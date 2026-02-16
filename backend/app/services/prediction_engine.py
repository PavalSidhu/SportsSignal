import logging
import math
from datetime import datetime
from pathlib import Path

import joblib
import numpy as np
from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Game, Prediction, Team
from app.services.feature_engineer import BASE_FEATURE_NAMES, FeatureEngineer
from app.utils.sport_config import get_sport_config

logger = logging.getLogger(__name__)

MODELS_DIR = Path(__file__).resolve().parent.parent.parent / "models"

# Check if SHAP is available
try:
    import shap
    HAS_SHAP = True
except ImportError:
    HAS_SHAP = False

# Human-readable labels for features
FEATURE_LABELS: dict[str, str] = {
    # Base features
    "elo_diff": "Team rating difference",
    "home_win_pct_10": "Recent form (home)",
    "away_win_pct_10": "Recent form (away)",
    "home_win_pct_last10": "Recent form (home)",
    "away_win_pct_last10": "Recent form (away)",
    "home_advantage": "Home court advantage",
    "home_ppg_20": "Offensive output (home)",
    "away_ppg_20": "Offensive output (away)",
    "home_ppg": "Offensive output (home)",
    "away_ppg": "Offensive output (away)",
    "home_papg_20": "Defensive rating (home)",
    "away_papg_20": "Defensive rating (away)",
    "home_papg": "Defensive rating (home)",
    "away_papg": "Defensive rating (away)",
    "rest_days_home": "Rest advantage (home)",
    "rest_days_away": "Rest advantage (away)",
    "is_back_to_back_home": "Back-to-back (home)",
    "is_back_to_back_away": "Back-to-back (away)",
    "h2h_home_wins_last5": "Head-to-head record",
    "is_postseason": "Playoff intensity",
    "home_streak": "Win streak (home)",
    "away_streak": "Win streak (away)",
    "home_margin_avg_10": "Scoring margin (home)",
    "away_margin_avg_10": "Scoring margin (away)",
    # NBA
    "home_efg_pct_10": "Shooting efficiency (home)",
    "away_efg_pct_10": "Shooting efficiency (away)",
    "home_tov_pct_10": "Turnover rate (home)",
    "away_tov_pct_10": "Turnover rate (away)",
    "home_ftr_10": "Free throw rate (home)",
    "away_ftr_10": "Free throw rate (away)",
    "home_oreb_pct_10": "Offensive rebounds (home)",
    "away_oreb_pct_10": "Offensive rebounds (away)",
    "home_net_rating_10": "Net rating (home)",
    "away_net_rating_10": "Net rating (away)",
    "home_pace_10": "Pace of play (home)",
    "away_pace_10": "Pace of play (away)",
    # NHL
    "home_save_pct_10": "Goaltending (home)",
    "away_save_pct_10": "Goaltending (away)",
    "home_shot_diff_10": "Shot differential (home)",
    "away_shot_diff_10": "Shot differential (away)",
    "home_pp_pct_10": "Power play (home)",
    "away_pp_pct_10": "Power play (away)",
    "home_pk_pct_10": "Penalty kill (home)",
    "away_pk_pct_10": "Penalty kill (away)",
    "home_goals_per_game_10": "Goals per game (home)",
    "away_goals_per_game_10": "Goals per game (away)",
    # MLB
    "home_ops_10": "Hitting (OPS, home)",
    "away_ops_10": "Hitting (OPS, away)",
    "home_era_10": "Pitching (ERA, home)",
    "away_era_10": "Pitching (ERA, away)",
    "home_whip_10": "Pitching (WHIP, home)",
    "away_whip_10": "Pitching (WHIP, away)",
    "home_k_bb_ratio_10": "Strikeout-walk ratio (home)",
    "away_k_bb_ratio_10": "Strikeout-walk ratio (away)",
    "home_runs_per_game_10": "Run scoring (home)",
    "away_runs_per_game_10": "Run scoring (away)",
    # Football (NFL/NCAAF)
    "home_yards_per_play_10": "Yards per play (home)",
    "away_yards_per_play_10": "Yards per play (away)",
    "home_tov_margin_10": "Turnover margin (home)",
    "away_tov_margin_10": "Turnover margin (away)",
    "home_third_down_pct_10": "Third down efficiency (home)",
    "away_third_down_pct_10": "Third down efficiency (away)",
}


class PredictionEngine:
    def __init__(self) -> None:
        self._models_cache: dict[str, dict] = {}

    def _load_models(self, sport: str) -> dict:
        """Load trained models for a sport. Uses cache for repeated access.

        Handles both new format (dict with metadata) and legacy format (bare pipeline).
        """
        if sport in self._models_cache:
            return self._models_cache[sport]

        win_path = MODELS_DIR / f"{sport}_win_model.joblib"
        home_score_path = MODELS_DIR / f"{sport}_home_score_model.joblib"
        away_score_path = MODELS_DIR / f"{sport}_away_score_model.joblib"

        if not win_path.exists():
            raise FileNotFoundError(
                f"No trained models found for sport={sport}. "
                f"Expected at {win_path}"
            )

        win_raw = joblib.load(win_path)

        # Helper to load model from either dict-with-metadata or bare format
        def _load_model(path):
            raw = joblib.load(path)
            if isinstance(raw, dict) and "model" in raw:
                return raw["model"]
            return raw

        # Detect format: new models are saved as dicts with metadata
        if isinstance(win_raw, dict) and "model" in win_raw:
            models = {
                "win": win_raw["model"],
                "feature_names": win_raw.get("feature_names"),
                "model_type": win_raw.get("model_type", "unknown"),
                "home_score": _load_model(home_score_path),
                "away_score": _load_model(away_score_path),
            }
        else:
            # Legacy format: bare pipeline
            models = {
                "win": win_raw,
                "feature_names": None,
                "model_type": "legacy_pipeline",
                "home_score": _load_model(home_score_path),
                "away_score": _load_model(away_score_path),
            }

        self._models_cache[sport] = models
        logger.info(
            "Loaded models for sport=%s (type=%s, features=%s)",
            sport,
            models["model_type"],
            len(models["feature_names"]) if models["feature_names"] else "legacy",
        )
        return models

    async def predict_game(self, game: Game, db: AsyncSession) -> dict | None:
        """Generate a prediction for a single game. Returns prediction data dict."""
        models = self._load_models(game.sport)

        # Use sport-aware feature engineer if model has feature names
        model_feature_names = models.get("feature_names")
        if model_feature_names and len(model_feature_names) > 14:
            fe = FeatureEngineer(db, sport=game.sport)
        else:
            fe = FeatureEngineer(db)

        features = await fe.compute_features(game)
        if features is None:
            logger.warning(
                "Could not compute features for game %d, skipping prediction",
                game.id,
            )
            return None

        feature_array = np.array([fe.to_array(features)])

        # Win probability
        win_proba = models["win"].predict_proba(feature_array)[0]
        home_win_prob = float(win_proba[1])
        away_win_prob = float(win_proba[0])

        # Score predictions
        raw_home = float(models["home_score"].predict(feature_array)[0])
        raw_away = float(models["away_score"].predict(feature_array)[0])
        predicted_total = max(raw_home, 0.0) + max(raw_away, 0.0)

        config = get_sport_config(game.sport)
        clamped_prob = max(0.01, min(0.99, home_win_prob))
        logit = math.log(clamped_prob / (1.0 - clamped_prob))
        predicted_spread = config.spread_calibration * logit

        raw_predicted_home = max((predicted_total + predicted_spread) / 2.0, 0.0)
        raw_predicted_away = max((predicted_total - predicted_spread) / 2.0, 0.0)

        predicted_home_score = round(raw_predicted_home)
        predicted_away_score = round(raw_predicted_away)
        if home_win_prob >= 0.5:
            if predicted_home_score <= predicted_away_score:
                predicted_home_score = predicted_away_score + 1
        else:
            if predicted_away_score <= predicted_home_score:
                predicted_away_score = predicted_home_score + 1

        predicted_spread = float(predicted_home_score - predicted_away_score)
        predicted_total = float(predicted_home_score + predicted_away_score)
        win_probability = home_win_prob

        if home_win_prob >= 0.5:
            predicted_winner_id = game.home_team_id
        else:
            predicted_winner_id = game.away_team_id

        quarter_predictions = await self._compute_period_predictions(
            game, predicted_home_score, predicted_away_score, db
        )

        # Explanation factors
        win_model = models["win"]
        key_factors = self._compute_factors(
            features, win_model, fe.FEATURE_NAMES, feature_array
        )

        model_certainty = max(home_win_prob, away_win_prob)
        confidence = self._apply_confidence(model_certainty, game)

        return {
            "game_id": game.id,
            "sport": game.sport,
            "prediction_date": datetime.utcnow(),
            "predicted_winner_id": predicted_winner_id,
            "win_probability": win_probability,
            "confidence": confidence,
            "predicted_home_score": float(predicted_home_score),
            "predicted_away_score": float(predicted_away_score),
            "predicted_spread": predicted_spread,
            "predicted_total": predicted_total,
            "quarter_predictions": quarter_predictions,
            "key_factors": key_factors,
        }

    async def _compute_period_predictions(
        self,
        game: Game,
        predicted_home_score: float,
        predicted_away_score: float,
        db: AsyncSession,
    ) -> dict:
        """Distribute predicted total scores into period-by-period predictions."""
        config = get_sport_config(game.sport)
        num_periods = config.num_periods

        home_pcts = await self._get_period_percentages(game.home_team_id, num_periods, db)
        away_pcts = await self._get_period_percentages(game.away_team_id, num_periods, db)

        home_periods = self._distribute_score(predicted_home_score, home_pcts)
        away_periods = self._distribute_score(predicted_away_score, away_pcts)

        return {"home": home_periods, "away": away_periods}

    @staticmethod
    def _distribute_score(total: float, pcts: list[float]) -> list[float]:
        """Distribute *total* across periods using *pcts*, ensuring the
        rounded values sum exactly to ``round(total, 1)``.

        Uses the largest-remainder method.
        """
        import math

        target = round(total, 1)
        target_tenths = round(target * 10)
        raw = [total * p for p in pcts]

        floored_tenths = [math.floor(round(v * 10, 6)) for v in raw]
        remainders = [round(v * 10, 6) - math.floor(round(v * 10, 6)) for v in raw]

        shortfall = target_tenths - sum(floored_tenths)

        if shortfall > 0:
            indices_by_remainder = sorted(
                range(len(remainders)), key=lambda i: remainders[i], reverse=True
            )
            for i in range(int(shortfall)):
                floored_tenths[indices_by_remainder[i]] += 1

        return [round(v / 10, 1) for v in floored_tenths]

    async def _get_period_percentages(
        self, team_id: int, num_periods: int, db: AsyncSession
    ) -> list[float]:
        """Get average period scoring percentages from last 20 games."""
        result = await db.execute(
            select(Game)
            .where(
                or_(
                    Game.home_team_id == team_id,
                    Game.away_team_id == team_id,
                ),
                Game.status == "Final",
            )
            .order_by(Game.game_date.desc())
            .limit(20)
        )
        games = result.scalars().all()

        period_totals = [0.0] * num_periods
        total_regulation_points = 0.0
        valid_count = 0

        for g in games:
            if g.home_team_id == team_id:
                period_scores = g.home_period_scores
            else:
                period_scores = g.away_period_scores

            if period_scores and len(period_scores) >= num_periods:
                regulation_sum = 0.0
                for i in range(num_periods):
                    period_totals[i] += period_scores[i]
                    regulation_sum += period_scores[i]
                total_regulation_points += regulation_sum
                valid_count += 1

        if valid_count > 0 and total_regulation_points > 0:
            return [pt / total_regulation_points for pt in period_totals]

        even = 1.0 / num_periods
        return [even] * num_periods

    @staticmethod
    def _compute_factors(
        features: dict,
        model,
        feature_names: list[str],
        feature_array: np.ndarray | None = None,
    ) -> list[dict]:
        """Compute explanation factors using SHAP (tree models) or coefficients (linear).

        For tree-based models (LightGBM via CalibratedClassifierCV), uses SHAP
        TreeExplainer for accurate feature importance.  Falls back to the
        coefficient-based method for linear models.
        """
        # Try SHAP for tree-based models
        if HAS_SHAP and feature_array is not None:
            base_model = _extract_tree_model(model)
            if base_model is not None:
                try:
                    explainer = shap.TreeExplainer(base_model)
                    shap_values = explainer.shap_values(feature_array)

                    # shap_values may be a list [class_0, class_1] for binary classification
                    if isinstance(shap_values, list):
                        sv = shap_values[1][0]  # class 1 (home win) SHAP values
                    else:
                        sv = shap_values[0]

                    impacts = []
                    for i, name in enumerate(feature_names):
                        impact = float(sv[i])
                        human_name = FEATURE_LABELS.get(name, name)
                        direction = "positive" if impact >= 0 else "negative"

                        if abs(impact) > 0.01:
                            detail = (
                                f"{human_name} favors the home team"
                                if direction == "positive"
                                else f"{human_name} favors the away team"
                            )
                        else:
                            detail = f"{human_name} has minimal impact"

                        impacts.append({
                            "factor": human_name,
                            "impact": round(impact, 4),
                            "direction": direction,
                            "detail": detail,
                        })

                    impacts.sort(key=lambda x: abs(x["impact"]), reverse=True)
                    return impacts[:5]
                except Exception:
                    logger.debug("SHAP failed, falling back to coefficient method")

        # Fallback: coefficient-based method for linear models
        if hasattr(model, "named_steps"):
            scaler = model.named_steps.get("scaler")
            clf = model.named_steps["model"]
        elif hasattr(model, "coef_"):
            scaler = None
            clf = model
        else:
            # Calibrated model without SHAP — use feature importance if available
            base = _extract_tree_model(model)
            if base is not None and hasattr(base, "feature_importances_"):
                importances = base.feature_importances_
                impacts = []
                for i, name in enumerate(feature_names):
                    imp = float(importances[i])
                    human_name = FEATURE_LABELS.get(name, name)
                    val = features.get(name, 0.0)
                    direction = "positive" if val >= 0 else "negative"
                    impacts.append({
                        "factor": human_name,
                        "impact": round(imp, 4),
                        "direction": direction,
                        "detail": f"{human_name} importance: {imp:.3f}",
                    })
                impacts.sort(key=lambda x: abs(x["impact"]), reverse=True)
                return impacts[:5]
            return []

        if not hasattr(clf, "coef_"):
            return []

        coefficients = clf.coef_[0]
        raw_values = np.array([features[name] for name in feature_names])

        if scaler is not None:
            scaled_values = scaler.transform(raw_values.reshape(1, -1))[0]
        else:
            scaled_values = raw_values

        impacts = []
        for i, name in enumerate(feature_names):
            coeff = coefficients[i]
            impact = float(scaled_values[i]) * coeff

            human_name = FEATURE_LABELS.get(name, name)
            direction = "positive" if impact >= 0 else "negative"

            if abs(impact) > 0.01:
                if direction == "positive":
                    detail = f"{human_name} favors the home team"
                else:
                    detail = f"{human_name} favors the away team"
            else:
                detail = f"{human_name} has minimal impact"

            impacts.append({
                "factor": human_name,
                "impact": round(float(impact), 4),
                "direction": direction,
                "detail": detail,
            })

        impacts.sort(key=lambda x: abs(x["impact"]), reverse=True)
        return impacts[:5]

    @staticmethod
    def _apply_confidence(raw_prob: float, game: Game) -> float:
        """Apply confidence adjustments based on available data quality."""
        confidence = raw_prob

        # No injury data available - reduce confidence
        confidence *= 0.90

        # Playoff games have more variance
        if game.is_postseason:
            confidence *= 0.92

        return round(confidence, 4)

    async def predict_games_batch(
        self, games: list[Game], db: AsyncSession
    ) -> list[Prediction]:
        """Generate and store predictions for a batch of games."""
        predictions: list[Prediction] = []

        for game in games:
            pred_data = await self.predict_game(game, db)
            if pred_data is None:
                continue

            prediction = Prediction(
                game_id=pred_data["game_id"],
                sport=pred_data["sport"],
                prediction_date=pred_data["prediction_date"],
                predicted_winner_id=pred_data["predicted_winner_id"],
                win_probability=pred_data["win_probability"],
                confidence=pred_data["confidence"],
                predicted_home_score=pred_data["predicted_home_score"],
                predicted_away_score=pred_data["predicted_away_score"],
                predicted_spread=pred_data["predicted_spread"],
                predicted_total=pred_data["predicted_total"],
                quarter_predictions=pred_data["quarter_predictions"],
                key_factors=pred_data["key_factors"],
            )
            db.add(prediction)
            predictions.append(prediction)

        await db.flush()
        logger.info("Generated %d predictions for %d games", len(predictions), len(games))
        return predictions


def _extract_tree_model(model):
    """Extract the underlying tree model from a CalibratedClassifierCV or similar wrapper."""
    # CalibratedClassifierCV wraps calibrated_classifiers_
    if hasattr(model, "calibrated_classifiers_"):
        for cc in model.calibrated_classifiers_:
            base = getattr(cc, "estimator", None)
            if base is not None and hasattr(base, "booster_"):
                return base
    # Direct LGBMClassifier
    if hasattr(model, "booster_"):
        return model
    return None
