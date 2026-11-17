"""XGBoost V1. Three timeframes, held-out final year, TreeSHAP reasons."""

from __future__ import annotations

import logging
import pickle
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import pandas as pd
import xgboost as xgb

from app.explain import top_reasons
from app.indicators import FEATURE_COLUMNS, add_indicators
from app.logic import FLAT_PIPS, MODEL_VERSION, PIP

log = logging.getLogger("trendlens.model")
CACHE = Path(__file__).resolve().parent.parent / ".cache"


def label_frame(frame: pd.DataFrame, timeframe: str) -> pd.DataFrame:
    df = frame.copy()
    future = df["close"].shift(-1) - df["close"]
    pips = future / PIP
    flat = FLAT_PIPS[timeframe]
    # 0 bearish, 1 bullish, 2 neutral
    labels = np.full(len(df), 2, dtype=int)
    labels[pips > flat] = 1
    labels[pips < -flat] = 0
    df["label"] = labels
    df.loc[future.isna(), "label"] = np.nan
    return df


def _matrix(df: pd.DataFrame) -> np.ndarray:
    return df[FEATURE_COLUMNS].to_numpy(dtype=np.float32)


def train_timeframe(frame: pd.DataFrame, timeframe: str) -> dict:
    featured = add_indicators(frame).dropna(subset=FEATURE_COLUMNS).copy()
    labeled = label_frame(featured, timeframe)
    usable = labeled.dropna(subset=["label"]).copy()
    usable["label"] = usable["label"].astype(int)
    oos_start = usable.index.max() - pd.Timedelta(days=365)
    train = usable[usable.index < oos_start]
    test = usable[usable.index >= oos_start]
    if train["label"].nunique() < 3 or len(train) < 200:
        raise RuntimeError(f"Not enough {timeframe} rows to train a 3-class model.")

    dtrain = xgb.DMatrix(train[FEATURE_COLUMNS], label=train["label"], feature_names=FEATURE_COLUMNS)
    params = {
        "objective": "multi:softprob",
        "num_class": 3,
        "max_depth": 4,
        "eta": 0.08,
        "subsample": 0.85,
        "colsample_bytree": 0.85,
        "min_child_weight": 8,
        "eval_metric": "mlogloss",
        "nthread": 2,
    }
    booster = xgb.train(params, dtrain, num_boost_round=80)
    accuracy = None
    if len(test):
        dtest = xgb.DMatrix(test[FEATURE_COLUMNS], feature_names=FEATURE_COLUMNS)
        probs = booster.predict(dtest)
        pred = probs.argmax(axis=1)
        accuracy = float((pred == test["label"].to_numpy()).mean())
    return {
        "timeframe": timeframe,
        "booster": booster,
        "oos_start": oos_start.to_pydatetime(),
        "train_rows": int(len(train)),
        "test_rows": int(len(test)),
        "accuracy": accuracy,
        "featured": featured,
    }


def predict_rows(bundle: dict, rows: pd.DataFrame) -> pd.DataFrame:
    out = rows.copy()
    matrix = xgb.DMatrix(out[FEATURE_COLUMNS], feature_names=FEATURE_COLUMNS)
    probs = bundle["booster"].predict(matrix)
    out["p_bear"] = probs[:, 0]
    out["p_bull"] = probs[:, 1]
    out["p_neutral"] = probs[:, 2]
    out["pred"] = probs.argmax(axis=1)
    mapping = {0: "bearish", 1: "bullish", 2: "neutral"}
    out["direction"] = [mapping[int(value)] for value in out["pred"]]
    out["confidence"] = out[["p_bear", "p_bull", "p_neutral"]].max(axis=1) * 100
    out["withheld"] = False
    forced = (out["direction"] != "neutral") & (out["confidence"] < 55)
    out.loc[forced, "direction"] = "neutral"
    out.loc[forced, "withheld"] = True
    return out


def predict_frame(bundle: dict) -> pd.DataFrame:
    featured = bundle["featured"]
    oos = featured[featured.index >= bundle["oos_start"]]
    return predict_rows(bundle, oos)


def shap_for_row(booster: xgb.Booster, row: pd.Series) -> list[tuple[str, float, float]]:
    matrix = xgb.DMatrix(pd.DataFrame([row[FEATURE_COLUMNS]]), feature_names=FEATURE_COLUMNS)
    try:
        contribs = booster.predict(matrix, pred_contribs=True)
        array = np.asarray(contribs)
        width = len(FEATURE_COLUMNS) + 1
        if array.ndim == 3:
            per_class = array[0]
        elif array.shape[-1] == width and array.ndim == 2 and array.shape[0] == 3:
            per_class = array
        else:
            flat = array.reshape(-1)
            per_class = flat.reshape(3, width)
        pred = int(np.argmax(booster.predict(matrix)[0]))
        values = per_class[pred][:-1]
        pairs = []
        for name, shap_value in zip(FEATURE_COLUMNS, values):
            raw = row[name]
            raw_f = None if raw != raw else float(raw)
            pairs.append((name, float(shap_value), raw_f))
    except (xgb.core.XGBoostError, ValueError):
        log.exception("TreeSHAP failed; falling back to feature magnitude")
        pairs = []
        for name in FEATURE_COLUMNS:
            raw = row[name]
            raw_f = 0.0 if raw != raw else float(raw)
            pairs.append((name, raw_f, raw_f))
    pairs.sort(key=lambda item: abs(item[1]), reverse=True)
    return pairs


def latest_from_row(bundle: dict, row: pd.Series, news_lines: list[str]) -> dict:
    direction = str(row["direction"])
    confidence = float(row["confidence"])
    withheld = bool(row.get("withheld", False))
    price = float(row["close"])
    atr = float(row["atr_14"]) if row["atr_14"] == row["atr_14"] else 0.0
    pairs = shap_for_row(bundle["booster"], row)
    tech_score = round(float((row["p_bull"] - row["p_bear"]) * 100))
    return {
        "timeframe": bundle["timeframe"],
        "tech_direction": direction,
        "tech_confidence": round(confidence, 1),
        "withheld": withheld,
        "price": round(price, 5),
        "atr": atr,
        "tech_score": max(-100, min(100, tech_score)),
        "reasons": top_reasons(pairs, news_lines),
        "features": {
            name: None if row[name] != row[name] else round(float(row[name]), 6) for name in FEATURE_COLUMNS
        },
        "as_of": row.name.to_pydatetime(),
        "probs": {
            "bearish": round(float(row["p_bear"]) * 100, 1),
            "bullish": round(float(row["p_bull"]) * 100, 1),
            "neutral": round(float(row["p_neutral"]) * 100, 1),
        },
    }


def save_model(payload: dict) -> Path:
    CACHE.mkdir(parents=True, exist_ok=True)
    path = CACHE / MODEL_VERSION
    with path.open("wb") as handle:
        pickle.dump(payload, handle)
    return path


def load_cached(cache_key: str) -> dict | None:
    path = CACHE / f"{cache_key}.pkl"
    if not path.exists():
        return None
    try:
        with path.open("rb") as handle:
            return pickle.load(handle)
    except (OSError, pickle.PickleError, EOFError):
        return None


def train_all(frames: dict[str, pd.DataFrame]) -> dict:
    started = datetime.now(timezone.utc)
    bundles = {}
    for timeframe, frame in frames.items():
        log.info("Training %s on %s rows", timeframe, len(frame))
        bundles[timeframe] = train_timeframe(frame, timeframe)
    dataset = sum(bundle["train_rows"] for bundle in bundles.values())
    accuracies = [bundle["accuracy"] for bundle in bundles.values() if bundle["accuracy"] is not None]
    record = {
        "trained_at": started,
        "dataset_size": dataset,
        "accuracy": float(np.mean(accuracies)) if accuracies else None,
        "version": MODEL_VERSION,
        "bundles": bundles,
    }
    save_model(record)
    log.info(
        "Retrain %s accuracy=%.3f rows=%s",
        MODEL_VERSION,
        record["accuracy"] or -1,
        dataset,
    )
    return record
