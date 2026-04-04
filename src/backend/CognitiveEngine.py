class CognitiveEngine():
    def __init__(self,parent=None):
        super().__init__(parent)
        self.processor = MathProcessor()
        
        self.last_action_time = time.time()
        self.inactivity_threshold = 60  
        
        self.eraser_count = 0
        self.eraser_threshold = 100       
        
        self.session_history = []
        self.is_helping = False
    def update(self,message):
        current_time=time.time()
        self.last_action_time=current_time

        if message.get("type")== "stroke":
            tool= message.get("tool")
            self;session_history.append(message)
        
        if tool="eraser":
            self.eraser_count+=1
        else:
            slef.eraser_count = max(0,self.eraser_count-0.5)
        
    def check_for_intervention(self):
        now=time.time()
        idle_time=now-self.last_action_time
        if idle_time > self.inactivity_threshold and not self.is_helping:
            self.is_helping = True
            return {
                "type": "tutor_message",
                "text": "You seem to be thinking a lot. Do you need some help ?",
                "role": "assistant"
            }

        if self.eraser_count>=self.eraser_threshold and not self.is_helping:
            self.is_helping=True
            self.eraser_count=0
            return{
                "type": "tutor_message"
                "text": "you seem to be a little bit frustrated. Do you need some help ?"
                "role": "assistant"
            }
        
        if idle_time < 5:
            self.is_helping = False 
        return None
        