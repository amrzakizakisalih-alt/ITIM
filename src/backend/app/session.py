"""
session – State per WebSocket connection.
"""

from domain.math.math_processor import MathProcessor
from domain.cognitive.act_r import ActR
from tutor.tutor import Tutor
from domain.exercises.document_processor import DocumentProcessor
from domain.exercises.exercise_generator import ExerciseGenerator
from core.profile_manager import ProfileManager
from domain.math.step_tracker import StepTracker
from input.gesture_recognizer import GestureRecognizer
from input.stroke_analyzer import StrokeAnalyzer
from input.stroke_buffer import StrokeBuffer
from domain.math.math_expert import MathExpert
from domain.exercises.exercise_library import ExerciseLibrary


class SessionState:
    """Encapsulates the state of a user session."""

    def __init__(self, user_id: str, llm_client, math_expert: MathExpert, exercise_library: ExerciseLibrary):
        self.user_id = user_id
        self.stroke_buffer = StrokeBuffer()
        self.math_processor = MathProcessor(llm_client=llm_client)
        self.actr = ActR(math_expert=math_expert)
        self.tutor = Tutor(llm_client=llm_client)
        self.tutor.bind_actr(self.actr)
        self.doc_processor = DocumentProcessor(llm_client=llm_client)
        self.exercise_gen = ExerciseGenerator()
        self.exercise_gen.library = exercise_library
        self.last_exercises = []
        self.document_text = ""
        self.detected_exercises = []
        self.profile_manager = ProfileManager(user_id)
        self.step_tracker = StepTracker(self.actr.mathExpert)
        self.gesture_recognizer = GestureRecognizer()
        self.stroke_analyzer = StrokeAnalyzer()
        self.ocr_task = None
        self.ocr_requests: dict = {}       # id -> asyncio.Future (capture full-page)
        self.ocr_request_counter = 0
        self.last_ocr_time = 0.0
        self.last_ocr_timestamp = 0.0        # timestamp of the last processed OCR
        self.last_latex_results: list = []  # OCR result deduplication
        self.stroke_debounce_task = None
        self.last_stroke_checkin_time = 0.0
        self.exercise_queue: list = []       # exercise queue in sequential mode (exam)
        self.exercise_queue_index: int = 0   # index of the current exercise in the queue


session_states: dict = {}  # ws_id -> SessionState
