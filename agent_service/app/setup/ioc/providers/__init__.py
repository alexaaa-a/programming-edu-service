from .decisions import DecisionProviders
from .kafka import KafkaProviders
from .logging import LoggingProviders
from .memory import MemoryProviders
from .http import HttpProviders
from .observability import ObservabilityProviders
from .redis import RedisProviders
from .eval_pipeline import EvalPipelineProviders
from .graph_memory import GraphMemoryProviders
from .graphs import LangGraphProviders
from .review_pipeline import ReviewPipelineProviders
from .career_puzzle import CareerPuzzleProviders
from .chat_pipeline import ChatPipelineProviders
from .health import HealthProviders
from .templates import TemplateProviders


all_providers = [
    *LoggingProviders,
    *MemoryProviders,
    *HttpProviders,
    *ObservabilityProviders,
    *DecisionProviders,
    *RedisProviders,
    *LangGraphProviders,
    *GraphMemoryProviders,
    *EvalPipelineProviders,
    *HealthProviders,
    *ChatPipelineProviders,
    *CareerPuzzleProviders,
    *TemplateProviders,
    *ReviewPipelineProviders,
    *KafkaProviders,
]

