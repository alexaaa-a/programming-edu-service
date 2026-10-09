from pydantic_core import MultiHostUrl
from pydantic_settings import BaseSettings, SettingsConfigDict


class MongoSettings(BaseSettings):
    host: str
    port: int
    username: str
    password: str
    name: str
    ssl: bool = False
    server_selection_timeout_ms: int = 5000

    model_config = SettingsConfigDict(env_prefix="AGENT_SERVICE_MONGO_")

    @property
    def connection_string(self) -> MultiHostUrl:
        return MultiHostUrl.build(
            scheme="mongodb",
            username=self.username,
            password=self.password,
            host=self.host,
            port=self.port,
        )


class TinyDbSettings(BaseSettings):
    chat_history_path: str = "/app/agent_service/data/chat_history.json"

    model_config = SettingsConfigDict(env_prefix="AGENT_SERVICE_TINYDB_")


class RedisSettings(BaseSettings):
    host: str
    port: int
    db: int
    retrieve_cache_ttl_sec: int
    password: str
    checkpoint_ttl_sec: int = 86_400

    model_config = SettingsConfigDict(env_prefix="AGENT_SERVICE_REDIS_")


class LoggingSettings(BaseSettings):
    level: str = "INFO"


class KafkaSettings(BaseSettings):
    bootstrap_servers: str
    topic_submission_created: str
    topic_submission_reviewed: str
    submission_review_consumer_group_id: str

    model_config = SettingsConfigDict(env_prefix="AGENT_SERVICE_KAFKA_")


class OpenAISettings(BaseSettings):
    api_key: str
    base_url: str
    model: str
    embedding_model: str = "text-embedding-3-small"
    embedding_base_url: str = ""
    embedding_api_key: str = ""
    temperature: float = 0.1
    reasoning_effort: str = "none"
    timeout_sec: float = 90.0

    model_config = SettingsConfigDict(env_prefix="AGENT_SERVICE_OPENAI_")


class JevSettings(BaseSettings):
    enabled: bool = True
    api_key: str = ""
    base_url: str = "https://openrouter.ai/api"
    model: str = "typesafe/jev-1.13"
    timeout_sec: float = 3.0
    min_confidence: float = 0.6
    failure_threshold: int = 3
    cooldown_sec: float = 60.0
    rerank_enabled: bool = True
    write_gate_enabled: bool = True

    model_config = SettingsConfigDict(env_prefix="AGENT_SERVICE_JEV_")

    @property
    def is_enabled(self) -> bool:
        return bool(self.enabled and self.api_key.strip() and self.model.strip())


class MemorySettings(BaseSettings):
    embedding_backend: str = "openai"
    persist_dir: str = "/app/agent_service/data/vector_store"
    max_retrieve_top_k: int = 8
    dedup_similarity: float = 0.92
    reinforce_enabled: bool = True

    model_config = SettingsConfigDict(env_prefix="AGENT_SERVICE_MEMORY_")


class Neo4jSettings(BaseSettings):
    uri: str = "bolt://neo4j:7687"
    user: str = "neo4j"
    password: str = ""
    database: str = "neo4j"

    model_config = SettingsConfigDict(env_prefix="AGENT_SERVICE_NEO4J_")

    @property
    def is_configured(self) -> bool:
        return bool(self.uri.strip() and self.password.strip())

    @property
    def safe_uri(self) -> str:
        raw = self.uri.strip()
        if "@" not in raw:
            return raw
        scheme, _, rest = raw.partition("://")
        return f"{scheme}://{rest.rpartition('@')[2]}" if rest else raw


class GraphMemorySettings(BaseSettings):
    enabled: bool = True
    model_extraction_enabled: bool = True
    extraction_model: str = ""
    embedding_dim: int = 1536
    max_coroutines: int = 4
    read_timeout_sec: float = 8.0
    write_timeout_sec: float = 25.0
    read_in_review: bool = True
    read_in_chat: bool = True
    ingest_enabled: bool = True
    ingest_batch_size: int = 4
    ingest_idle_sleep_sec: float = 5.0
    queue_lease_sec: int = 300
    queue_max_attempts: int = 4
    consolidation_enabled: bool = True
    consolidation_interval_sec: float = 21_600.0
    consolidation_first_delay_sec: float = 300.0
    consolidation_max_students: int = 200

    model_config = SettingsConfigDict(env_prefix="AGENT_SERVICE_GRAPH_MEMORY_")


class ChatHistorySettings(BaseSettings):
    max_messages: int = 20

    model_config = SettingsConfigDict(env_prefix="AGENT_SERVICE_CHAT_HISTORY_")


class SubmissionGatewaySettings(BaseSettings):
    url: str = "http://submission_service:8000"
    timeout_sec: float = 5.0
    internal_token: str = ""

    model_config = SettingsConfigDict(env_prefix="AGENT_SERVICE_SUBMISSION_")


class UserGatewaySettings(BaseSettings):
    url: str = "http://user_service:8000"
    timeout_sec: float = 5.0

    model_config = SettingsConfigDict(env_prefix="AGENT_SERVICE_USER_")


class TemplateSettings(BaseSettings):
    enabled: bool = True
    max_repair_rounds: int = 1

    model_config = SettingsConfigDict(env_prefix="AGENT_SERVICE_TEMPLATES_")


class CareerSettings(BaseSettings):
    token: str = ""

    model_config = SettingsConfigDict(env_prefix="AGENT_SERVICE_CAREER_")


class TokenSettings(BaseSettings):
    secret_key: str = ""
    algorithm: str = "HS256"
    allow_dev_auth: bool = False

    model_config = SettingsConfigDict(env_prefix="AGENT_SERVICE_TOKEN_")


class LangfuseSettings(BaseSettings):
    enabled: bool = False
    public_key: str = ""
    secret_key: str = ""
    host: str = "http://localhost:4000"
    environment: str = "local"
    debug: bool = False
    sample_rate: float = 1.0

    model_config = SettingsConfigDict(env_prefix="AGENT_SERVICE_LANGFUSE_")

    @property
    def is_enabled(self) -> bool:
        return bool(
            self.enabled
            and self.public_key.strip()
            and self.secret_key.strip()
            and self.host.strip()
        )


class Settings(BaseSettings):
    logging_settings: LoggingSettings = LoggingSettings()  # type: ignore[call-arg]
    kafka_settings: KafkaSettings = KafkaSettings()  # type: ignore[call-arg]
    openai_settings: OpenAISettings = OpenAISettings()  # type: ignore[call-arg]
    jev_settings: JevSettings = JevSettings()
    memory_settings: MemorySettings = MemorySettings()
    neo4j_settings: Neo4jSettings = Neo4jSettings()
    graph_memory_settings: GraphMemorySettings = GraphMemorySettings()
    mongo_settings: MongoSettings = MongoSettings()  # type: ignore[call-arg]
    tinydb_settings: TinyDbSettings = TinyDbSettings()
    chat_history_settings: ChatHistorySettings = ChatHistorySettings()  # type: ignore[call-arg]
    redis_settings: RedisSettings = RedisSettings()  # type: ignore[call-arg]
    langfuse_settings: LangfuseSettings = LangfuseSettings()
    submission_gateway_settings: SubmissionGatewaySettings = SubmissionGatewaySettings()
    user_gateway_settings: UserGatewaySettings = UserGatewaySettings()
    template_settings: TemplateSettings = TemplateSettings()
    career_settings: CareerSettings = CareerSettings()
    token_settings: TokenSettings = TokenSettings()

    model_config = SettingsConfigDict(env_prefix="")
