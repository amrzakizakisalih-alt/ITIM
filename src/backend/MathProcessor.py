import sympy
from PIL import Image, ImageDraw
from pix2tex.cli import LateOCR
from latex2sympy2 import latex2sympy
class MathProcessor():
    def __init__(self,parent=None):
        super().__init__(parent)
        self.Page_W = 794
        self.Page_H = 1123
        self.model= laTexOCR()

    def set_Page_W(self,Page_W)
        return self.Page_W=Page_W
    
    def set_Page_H(self,Page_H)
        return self.Page_H=Page_H

    def get_strokes_to_LateX(self,strokes,model):
        img = Image.new('RGB', (PAGE_W, PAGE_H), 'white')
        draw = ImageDraw.Draw(img)

        for stroke in strokes:
            points = [(p['x'], p['y']) for p in stroke['points']]
            if len(points) < 2: continue

            if stroke.get('tool') == 'eraser':
                draw.line(points, fill='white', width=int(stroke.get('width', 30)))
            else:
                draw.line(points, fill='black', width=int(stroke.get('width', 2)))

        return self.model(img)
    
    def get_sympy_expr(self,latex_str):
        return latex2sympy(latex_str)
    
    def get_AST(self,expr):
        if expr is None:
            return None     
        node = {
            "type": str(expr.func.__name__), 
            "content": str(expr)
        }
        if expr.args:
            node["children"] = [self.get_ast(arg) for arg in expr.args]
        
        return node




    