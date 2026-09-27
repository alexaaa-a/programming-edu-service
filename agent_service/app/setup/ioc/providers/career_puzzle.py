from dishka import Provider, Scope, provide

from agent_service.app.application.career_puzzle import CareerPuzzleUseCase
from agent_service.app.application.interfaces.llm import LLMInterface


class CareerPuzzleProvider(Provider):
    @provide(scope=Scope.REQUEST)
    def career_puzzle(self, llm: LLMInterface) -> CareerPuzzleUseCase:
        return CareerPuzzleUseCase(llm)


CareerPuzzleProviders = [CareerPuzzleProvider()]
