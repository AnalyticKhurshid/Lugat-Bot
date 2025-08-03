from aiogram.fsm.state import StatesGroup, State

class QuizStates(StatesGroup):
    choosing_level = State()
    choosing_count = State()
    custom_count = State()
    asking_question = State()
