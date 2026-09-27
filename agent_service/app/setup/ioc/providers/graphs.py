from dishka import Provider, Scope, provide

from agent_service.app.application.interfaces.run_checkpoint_store import RunCheckpointStore
from agent_service.app.infrastructure.checkpoints.langgraph_saver import StoreBackedCheckpointSaver


class LangGraphCheckpointerProvider(Provider):
    @provide(scope=Scope.APP)
    def langgraph_checkpointer(self, store: RunCheckpointStore) -> StoreBackedCheckpointSaver:
        return StoreBackedCheckpointSaver(store)


LangGraphProviders = [LangGraphCheckpointerProvider()]
