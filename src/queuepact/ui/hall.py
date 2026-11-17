from nicegui.element import Element


class AdmissionHall(Element, component='hall.js'):
    def __init__(self, on_select):
        super().__init__()
        self._props['model'] = self.empty_model()
        self.on('select', lambda e: on_select(e.args))

    def present(self, model):
        self._props['model'] = {**self.empty_model(),**model}
        self.update()

    @staticmethod
    def empty_model():
        return dict(height=548,width=1000,markers=[],zones=[],desks=[],generation=0,playing=False,speed=1)
