from .decisions import DecisionProviders
from .kafka import KafkaProviders
from .logging import LoggingProviders
from .memory import MemoryProviders
from .http import HttpProviders
from .observability import ObservabilityProviders
from .redis import RedisProviders
from .eval_pipeline import EvalPipelineProviders
from .graphs import LangGraphProviders
from .review_pipeline import ReviewPipelineProviders
from .career_puzzle import CareerPuzzleProviders
from .chat_pipeline import ChatPipelineProviders
from .health import HealthProviders


all_providers = [
    *LoggingProviders,
    *MemoryProviders,
    *HttpProviders,
    *ObservabilityProviders,
    *DecisionProviders,
    *RedisProviders,
    *LangGraphProviders,
    *EvalPipelineProviders,
    *HealthProviders,
    *ChatPipelineProviders,
    *CareerPuzzleProviders,
    *ReviewPipelineProviders,
    *KafkaProviders,
]

