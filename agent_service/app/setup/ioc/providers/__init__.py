from .kafka import KafkaProviders
from .logging import LoggingProviders
from .memory import MemoryProviders
from .http import HttpProviders
from .observability import ObservabilityProviders
from .redis import RedisProviders
from .eval_pipeline import EvalPipelineProviders
from .review_pipeline import ReviewPipelineProviders
from .chat_pipeline import ChatPipelineProviders
from .health import HealthProviders


all_providers = [
    *LoggingProviders,
    *MemoryProviders,
    *HttpProviders,
    *ObservabilityProviders,
    *RedisProviders,
    *EvalPipelineProviders,
    *HealthProviders,
    *ChatPipelineProviders,
    *ReviewPipelineProviders,
    *KafkaProviders,
]

