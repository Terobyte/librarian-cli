class LibError(Exception): ...
class DetectError(LibError): ...          # неизвестный формат
class ExtractError(LibError): ...
class ScanError(ExtractError): ...        # PDF без текстового слоя
class EncryptedError(ExtractError): ...   # PDF под паролем (пустой пароль уже испробован)
class BrokenFileError(ExtractError): ...  # битый zip/xml, недекодируемый текст, zip-bomb
class LimitError(ExtractError): ...       # превышен лимит 6.0 (размер, таймаут)
class UnknownBookError(LibError): ...     # id не найден (get/info/rm)
