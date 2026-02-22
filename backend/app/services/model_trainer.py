import json
import logging
from datetime import datetime, timezone
from pathlib import Path

import joblib
import numpy as np
from sklearn.calibration import CalibratedClassifierCV
from sklearn.linear_model import LogisticRegression, RidgeCV
from sklearn.metrics import brier_score_loss, log_loss, mean_absolute_error
from sklearn.model_selection import TimeSeriesSplit, cross_val_score
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import StandardScaler
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Game
from app.services.feature_engineer import FeatureEngineer

logger = logging.getLogger(__name__)

MODELS_DIR = Path(__file__).resolve().parent.parent.parent / "models"

# Check if LightGBM is available
try:
    from lightgbm import LGBMClassifier, LGBMRegressor
    HAS_LIGHTGBM = True
except ImportError:
    HAS_LIGHTGBM = False
    logger.info("LightGBM not installed, falling back to LogisticRegression/RidgeCV")

# Check if Optuna is available
try:
    import optuna
    optuna.logging.set_verbosity(optuna.logging.WARNING)
    HAS_OPTUNA = True
except ImportError:
    HAS_OPTUNA = False


# Default LightGBM hyperparameters per sport
# Tuned based on audit findings: low-scoring sports (NHL, MLB) and small-sample
# sports (NFL) need heavier regularization to avoid overfitting.
DEFAULT_LGBM_PARAMS: dict[str, dict] = {
    "default": {
        "n_estimators": 500,
        "learning_rate": 0.05,
        "max_depth": 6,
        "num_leaves": 31,
        "min_child_samples": 20,
        "subsample": 0.8,
        "colsample_bytree": 0.8,
        "reg_alpha": 0.1,
        "reg_lambda": 1.0,
        "is_unbalance": True,
        "random_state": 42,
        "verbose": -1,
    },
    "NBA": {
        "n_estimators": 600,
        "learning_rate": 0.04,
        "max_depth": 6,
        "num_leaves": 31,
        "min_child_samples": 20,
        "subsample": 0.8,
        "colsample_bytree": 0.8,
        "reg_alpha": 0.1,
        "reg_lambda": 1.0,
        "is_unbalance": True,
        "random_state": 42,
        "verbose": -1,
    },
    "NHL": {
        "n_estimators": 400,
        "learning_rate": 0.03,
        "max_depth": 4,
        "num_leaves": 15,
        "min_child_samples": 30,
        "subsample": 0.7,
        "colsample_bytree": 0.7,
        "reg_alpha": 1.0,
        "reg_lambda": 5.0,
        "is_unbalance": True,
        "random_state": 42,
        "verbose": -1,
    },
    "MLB": {
        "n_estimators": 400,
        "learning_rate": 0.03,
        "max_depth": 4,
        "num_leaves": 15,
        "min_child_samples": 30,
        "subsample": 0.7,
        "colsample_bytree": 0.7,
        "reg_alpha": 1.0,
        "reg_lambda": 5.0,
        "is_unbalance": True,
        "random_state": 42,
        "verbose": -1,
    },
    "NFL": {
        "n_estimators": 300,
        "learning_rate": 0.02,
        "max_depth": 3,
        "num_leaves": 8,
        "min_child_samples": 40,
        "subsample": 0.7,
        "colsample_bytree": 0.6,
        "reg_alpha": 2.0,
        "reg_lambda": 10.0,
        "is_unbalance": True,
        "random_state": 42,
        "verbose": -1,
    },
    "NCAAF": {
        "n_estimators": 300,
        "learning_rate": 0.03,
        "max_depth": 4,
        "num_leaves": 15,
        "min_child_samples": 30,
        "subsample": 0.7,
        "colsample_bytree": 0.7,
        "reg_alpha": 1.0,
        "reg_lambda": 5.0,
        "is_unbalance": True,
        "random_state": 42,
        "verbose": -1,
    },
}


class ModelTrainer:
    def __init__(self) -> None:
        MODELS_DIR.mkdir(parents=True, exist_ok=True)

    async def train(
        self,
        sport: str,
        db: AsyncSession,
        tune: bool = False,
        use_lightgbm: bool = True,
    ) -> dict:
        """Train prediction models for a given sport.

        Args:
            sport: Sport code (NBA, NHL, MLB, etc.)
            db: Database session
            tune: Whether to run Optuna hyperparameter tuning
            use_lightgbm: Whether to use LightGBM (falls back to linear if not installed)

        Returns:
            Metrics dict with training results.
        """
        logger.info("Starting model training for sport=%s", sport)

        result = await db.execute(
            select(Game)
            .where(Game.sport == sport, Game.status == "Final")
            .order_by(Game.game_date.asc())
        )
        games = result.scalars().all()

        if not games:
            logger.warning("No completed games found for sport=%s", sport)
            return {"error": "No completed games found"}

        # Use sport-aware feature engineer
        fe = FeatureEngineer(db, sport=sport)
        X_list: list[list[float]] = []
        y_win_list: list[int] = []
        y_home_score_list: list[float] = []
        y_away_score_list: list[float] = []

        for game in games:
            features = await fe.compute_features(game)
            if features is None:
                continue
            if game.home_score is None or game.away_score is None:
                continue

            X_list.append(fe.to_array(features))
            y_win_list.append(1 if game.home_score > game.away_score else 0)
            y_home_score_list.append(float(game.home_score))
            y_away_score_list.append(float(game.away_score))

        if len(X_list) < 50:
            logger.warning(
                "Insufficient training data for sport=%s: only %d samples",
                sport, len(X_list),
            )
            return {"error": f"Insufficient training data: {len(X_list)} samples"}

        X = np.array(X_list)
        y_win = np.array(y_win_list)
        y_home_score = np.array(y_home_score_list)
        y_away_score = np.array(y_away_score_list)

        logger.info(
            "Collected %d games with %d features for sport=%s",
            len(X_list), X.shape[1], sport,
        )

        # Symmetric augmentation: add away-perspective mirror of each game
        # to eliminate inherent home bias in the model intercept
        X, y_win, y_home_score, y_away_score = self._augment_symmetric(
            X, y_win, y_home_score, y_away_score, fe.FEATURE_NAMES,
        )
        logger.info("After symmetric augmentation: %d samples", len(X))

        tscv = TimeSeriesSplit(n_splits=5)
        use_lgbm = use_lightgbm and HAS_LIGHTGBM

        if use_lgbm:
            metrics = self._train_lightgbm(
                X, y_win, y_home_score, y_away_score,
                sport, fe.FEATURE_NAMES, tscv, tune,
            )
        else:
            metrics = self._train_linear(
                X, y_win, y_home_score, y_away_score,
                sport, fe.FEATURE_NAMES, tscv,
            )

        # Save training metrics JSON
        metrics_path = MODELS_DIR / f"{sport}_training_metrics.json"
        with open(metrics_path, "w") as f:
            json.dump(metrics, f, indent=2, default=str)
        logger.info("Training metrics saved to %s", metrics_path)

        return metrics

    def _train_lightgbm(
        self,
        X: np.ndarray,
        y_win: np.ndarray,
        y_home_score: np.ndarray,
        y_away_score: np.ndarray,
        sport: str,
        feature_names: list[str],
        tscv: TimeSeriesSplit,
        tune: bool,
    ) -> dict:
        """Train LightGBM models with optional Optuna tuning and Platt calibration."""
        logger.info("Training with LightGBM for sport=%s", sport)

        # Get hyperparameters
        if tune and HAS_OPTUNA:
            logger.info("Running Optuna hyperparameter tuning...")
            best_params = self._tune_hyperparams(X, y_win, tscv)
            logger.info("Best params: %s", best_params)
        else:
            base_params = DEFAULT_LGBM_PARAMS.get(sport, DEFAULT_LGBM_PARAMS["default"])
            best_params = base_params.copy()

        # Win model: LGBMClassifier with calibration
        win_model = LGBMClassifier(**best_params)

        # Cross-validate before calibration
        accuracy_scores = cross_val_score(
            LGBMClassifier(**best_params), X, y_win, cv=tscv, scoring="accuracy",
        )
        accuracy = float(accuracy_scores.mean())

        # Additional CV metrics
        log_loss_scores = cross_val_score(
            LGBMClassifier(**best_params), X, y_win, cv=tscv, scoring="neg_log_loss",
        )
        cv_log_loss = float(-log_loss_scores.mean())

        # Brier score via manual CV
        brier_scores = []
        for train_idx, val_idx in tscv.split(X):
            m = LGBMClassifier(**best_params)
            m.fit(X[train_idx], y_win[train_idx])
            proba = m.predict_proba(X[val_idx])[:, 1]
            brier_scores.append(brier_score_loss(y_win[val_idx], proba))
        cv_brier = float(np.mean(brier_scores))

        # Train final win model with Platt calibration (using tscv to avoid temporal leakage)
        calibrated_model = CalibratedClassifierCV(
            win_model, method="sigmoid", cv=tscv,
        )
        calibrated_model.fit(X, y_win)

        # Score models: LGBMRegressor (filter out classifier-only params)
        score_params = {
            k: v for k, v in best_params.items()
            if k not in ("verbose", "is_unbalance")
        }
        score_params["verbose"] = -1

        home_score_model = LGBMRegressor(**score_params)
        away_score_model = LGBMRegressor(**score_params)

        home_score_model.fit(X, y_home_score)
        away_score_model.fit(X, y_away_score)

        # Score MAE via CV
        home_mae_scores = cross_val_score(
            LGBMRegressor(**score_params), X, y_home_score,
            cv=tscv, scoring="neg_mean_absolute_error",
        )
        away_mae_scores = cross_val_score(
            LGBMRegressor(**score_params), X, y_away_score,
            cv=tscv, scoring="neg_mean_absolute_error",
        )
        home_mae = float(-home_mae_scores.mean())
        away_mae = float(-away_mae_scores.mean())

        logger.info(
            "LightGBM CV for sport=%s: accuracy=%.3f, log_loss=%.3f, "
            "brier=%.3f, home_mae=%.2f, away_mae=%.2f",
            sport, accuracy, cv_log_loss, cv_brier, home_mae, away_mae,
        )

        # Feature importance from the uncalibrated model
        # Re-fit a plain model to get feature_importances_
        plain_model = LGBMClassifier(**best_params)
        plain_model.fit(X, y_win)
        importance = dict(zip(feature_names, plain_model.feature_importances_.tolist()))

        # Save models (bare, no Pipeline)
        win_path = MODELS_DIR / f"{sport}_win_model.joblib"
        home_score_path = MODELS_DIR / f"{sport}_home_score_model.joblib"
        away_score_path = MODELS_DIR / f"{sport}_away_score_model.joblib"

        # Save with metadata
        model_data = {
            "model": calibrated_model,
            "feature_names": feature_names,
            "model_type": "lightgbm_calibrated",
        }
        joblib.dump(model_data, win_path)
        home_score_data = {
            "model": home_score_model,
            "feature_names": feature_names,
            "model_type": "lightgbm_regressor",
        }
        away_score_data = {
            "model": away_score_model,
            "feature_names": feature_names,
            "model_type": "lightgbm_regressor",
        }
        joblib.dump(home_score_data, home_score_path)
        joblib.dump(away_score_data, away_score_path)

        logger.info("LightGBM models saved to %s", MODELS_DIR)

        return {
            "sport": sport,
            "model_type": "lightgbm",
            "training_samples": len(X),
            "feature_count": X.shape[1],
            "feature_names": feature_names,
            "accuracy": accuracy,
            "log_loss": cv_log_loss,
            "brier_score": cv_brier,
            "home_score_mae": home_mae,
            "away_score_mae": away_mae,
            "feature_importance": importance,
            "best_hyperparams": best_params,
            "training_date": datetime.now(timezone.utc).isoformat(),
        }

    def _train_linear(
        self,
        X: np.ndarray,
        y_win: np.ndarray,
        y_home_score: np.ndarray,
        y_away_score: np.ndarray,
        sport: str,
        feature_names: list[str],
        tscv: TimeSeriesSplit,
    ) -> dict:
        """Train with LogisticRegression/RidgeCV (fallback when LightGBM unavailable)."""
        logger.info("Training with LogisticRegression/RidgeCV for sport=%s", sport)

        win_pipeline = Pipeline([
            ("scaler", StandardScaler()),
            ("model", LogisticRegression(C=1.0, max_iter=2000)),
        ])
        home_score_pipeline = Pipeline([
            ("scaler", StandardScaler()),
            ("model", RidgeCV(alphas=[0.01, 0.1, 1.0, 10.0, 100.0])),
        ])
        away_score_pipeline = Pipeline([
            ("scaler", StandardScaler()),
            ("model", RidgeCV(alphas=[0.01, 0.1, 1.0, 10.0, 100.0])),
        ])

        win_pipeline.fit(X, y_win)
        home_score_pipeline.fit(X, y_home_score)
        away_score_pipeline.fit(X, y_away_score)

        accuracy_scores = cross_val_score(
            Pipeline([("scaler", StandardScaler()), ("model", LogisticRegression(C=1.0, max_iter=2000))]),
            X, y_win, cv=tscv, scoring="accuracy",
        )
        accuracy = float(accuracy_scores.mean())

        home_mae_scores = cross_val_score(
            Pipeline([("scaler", StandardScaler()), ("model", RidgeCV(alphas=[0.01, 0.1, 1.0, 10.0, 100.0]))]),
            X, y_home_score, cv=tscv, scoring="neg_mean_absolute_error",
        )
        away_mae_scores = cross_val_score(
            Pipeline([("scaler", StandardScaler()), ("model", RidgeCV(alphas=[0.01, 0.1, 1.0, 10.0, 100.0]))]),
            X, y_away_score, cv=tscv, scoring="neg_mean_absolute_error",
        )
        home_mae = float(-home_mae_scores.mean())
        away_mae = float(-away_mae_scores.mean())

        logger.info(
            "Linear CV for sport=%s: accuracy=%.3f, home_mae=%.2f, away_mae=%.2f",
            sport, accuracy, home_mae, away_mae,
        )

        # Save pipelines (includes scaler + model)
        win_path = MODELS_DIR / f"{sport}_win_model.joblib"
        home_score_path = MODELS_DIR / f"{sport}_home_score_model.joblib"
        away_score_path = MODELS_DIR / f"{sport}_away_score_model.joblib"

        # Save with metadata for backward compatibility detection
        model_data = {
            "model": win_pipeline,
            "feature_names": feature_names,
            "model_type": "linear_pipeline",
        }
        joblib.dump(model_data, win_path)
        home_score_data = {
            "model": home_score_pipeline,
            "feature_names": feature_names,
            "model_type": "linear_pipeline",
        }
        away_score_data = {
            "model": away_score_pipeline,
            "feature_names": feature_names,
            "model_type": "linear_pipeline",
        }
        joblib.dump(home_score_data, home_score_path)
        joblib.dump(away_score_data, away_score_path)

        logger.info("Linear models saved to %s", MODELS_DIR)

        return {
            "sport": sport,
            "model_type": "linear",
            "training_samples": len(X),
            "feature_count": X.shape[1],
            "feature_names": feature_names,
            "accuracy": accuracy,
            "home_score_mae": home_mae,
            "away_score_mae": away_mae,
            "training_date": datetime.now(timezone.utc).isoformat(),
        }

    @staticmethod
    def _augment_symmetric(
        X: np.ndarray,
        y_win: np.ndarray,
        y_home_score: np.ndarray,
        y_away_score: np.ndarray,
        feature_names: list[str],
    ) -> tuple[np.ndarray, np.ndarray, np.ndarray, np.ndarray]:
        """Double training data by adding away-perspective mirror of each game.

        For each sample, creates a flipped version where home/away features are
        swapped and the label is inverted. This teaches the model that the same
        matchup from the other side should give complementary probabilities,
        eliminating inherent home bias in the model intercept.
        """
        X_flip = np.copy(X)

        for i, name in enumerate(feature_names):
            if name == "elo_diff":
                X_flip[:, i] = -X[:, i]
            elif name == "h2h_home_wins_last5":
                X_flip[:, i] = 1.0 - X[:, i]
            elif name.startswith("home_"):
                away_name = "away_" + name[5:]
                if away_name in feature_names:
                    j = feature_names.index(away_name)
                    X_flip[:, i] = X[:, j]
                    X_flip[:, j] = X[:, i]

        return (
            np.concatenate([X, X_flip]),
            np.concatenate([y_win, 1 - y_win]),
            np.concatenate([y_home_score, y_away_score]),
            np.concatenate([y_away_score, y_home_score]),
        )

    @staticmethod
    def _tune_hyperparams(X: np.ndarray, y: np.ndarray, tscv) -> dict:
        """Run Optuna hyperparameter search for LightGBM."""
        def objective(trial):
            params = {
                "n_estimators": trial.suggest_int("n_estimators", 100, 1000),
                "learning_rate": trial.suggest_float("learning_rate", 0.01, 0.3, log=True),
                "max_depth": trial.suggest_int("max_depth", 3, 10),
                "num_leaves": trial.suggest_int("num_leaves", 15, 63),
                "min_child_samples": trial.suggest_int("min_child_samples", 5, 50),
                "subsample": trial.suggest_float("subsample", 0.6, 1.0),
                "colsample_bytree": trial.suggest_float("colsample_bytree", 0.6, 1.0),
                "reg_alpha": trial.suggest_float("reg_alpha", 1e-3, 10.0, log=True),
                "reg_lambda": trial.suggest_float("reg_lambda", 1e-3, 10.0, log=True),
                "is_unbalance": True,
                "random_state": 42,
                "verbose": -1,
            }
            model = LGBMClassifier(**params)
            scores = cross_val_score(model, X, y, cv=tscv, scoring="accuracy")
            return scores.mean()

        study = optuna.create_study(direction="maximize")
        study.optimize(objective, n_trials=50, show_progress_bar=False)

        best = study.best_params
        best["random_state"] = 42
        best["verbose"] = -1
        return best
