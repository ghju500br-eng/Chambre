"""Sources surveillées. Chaque source renvoie des offres ou lève ErreurSource."""


class ErreurSource(Exception):
    def __init__(self, message: str, bloque: bool = False):
        super().__init__(message)
        self.bloque = bloque
