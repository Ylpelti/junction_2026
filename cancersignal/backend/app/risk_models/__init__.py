"""Risk models kept separate from the rule table and language model."""

from app.risk_models.qcancer_2013 import QCancer2013Input, qcancer_prediction

__all__ = ["QCancer2013Input", "qcancer_prediction"]
