from .common import common_provider
from .db import db_provider
from .kafka import kafka_provider
from .services import service_provider
from .use_case import use_case_provider


all_providers = [*common_provider, *db_provider, *kafka_provider, *service_provider, *use_case_provider]
