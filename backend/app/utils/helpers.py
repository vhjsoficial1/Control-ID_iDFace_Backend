"""
Funções auxiliares e utilitárias para o sistema iDFace
Contém helpers para validação, formatação, conversão e outras utilidades
"""
from typing import Optional, List, Dict, Any, Union
from datetime import datetime, time, timedelta
import re
import base64
import hashlib
import secrets
import string
from functools import wraps
import logging

logger = logging.getLogger(__name__)


# ==================== Date & Time Helpers ====================

def seconds_to_time(seconds: int) -> str:
    """
    Converte segundos desde meia-noite para formato HH:MM
    
    Args:
        seconds: Segundos desde meia-noite (0-86400)
    
    Returns:
        String no formato "HH:MM"
    
    Example:
        >>> seconds_to_time(3600)
        "01:00"
        >>> seconds_to_time(43200)
        "12:00"
    """
    if seconds < 0 or seconds > 86400:
        raise ValueError("Segundos deve estar entre 0 e 86400")
    
    hours = seconds // 3600
    minutes = (seconds % 3600) // 60
    return f"{hours:02d}:{minutes:02d}"


def time_to_seconds(time_str: str) -> int:
    """
    Converte formato HH:MM para segundos desde meia-noite
    
    Args:
        time_str: String no formato "HH:MM"
    
    Returns:
        Segundos desde meia-noite
    
    Example:
        >>> time_to_seconds("01:00")
        3600
        >>> time_to_seconds("12:30")
        45000
    """
    try:
        hours, minutes = map(int, time_str.split(':'))
        
        if hours < 0 or hours > 23:
            raise ValueError("Horas deve estar entre 0 e 23")
        
        if minutes < 0 or minutes > 59:
            raise ValueError("Minutos deve estar entre 0 e 59")
        
        return hours * 3600 + minutes * 60
    except ValueError as e:
        raise ValueError(f"Formato inválido. Use HH:MM. Erro: {str(e)}")


def format_datetime(dt: datetime, format_type: str = "default") -> str:
    """
    Formata datetime para diferentes formatos
    
    Args:
        dt: Objeto datetime
        format_type: Tipo de formato (default, date, time, full, iso)
    
    Returns:
        String formatada
    """
    formats = {
        "default": "%d/%m/%Y %H:%M",
        "date": "%d/%m/%Y",
        "time": "%H:%M:%S",
        "full": "%d/%m/%Y %H:%M:%S",
        "iso": "%Y-%m-%dT%H:%M:%S",
        "filename": "%Y%m%d_%H%M%S"
    }
    
    format_str = formats.get(format_type, formats["default"])
    return dt.strftime(format_str)


def is_within_time_range(
    check_time: datetime,
    start: Optional[datetime] = None,
    end: Optional[datetime] = None
) -> bool:
    """
    Verifica se um datetime está dentro de um range
    
    Args:
        check_time: Tempo a verificar
        start: Início do range (None = sem limite)
        end: Fim do range (None = sem limite)
    
    Returns:
        True se estiver dentro do range
    """
    if start and check_time < start:
        return False
    
    if end and check_time > end:
        return False
    
    return True


def get_day_of_week(dt: datetime) -> str:
    """
    Retorna dia da semana em português
    
    Args:
        dt: Objeto datetime
    
    Returns:
        Nome do dia em português
    """
    days = {
        0: "Segunda-feira",
        1: "Terça-feira",
        2: "Quarta-feira",
        3: "Quinta-feira",
        4: "Sexta-feira",
        5: "Sábado",
        6: "Domingo"
    }
    return days[dt.weekday()]


# ==================== String Helpers ====================

def sanitize_string(text: str, max_length: Optional[int] = None) -> str:
    """
    Limpa e sanitiza uma string
    
    Args:
        text: String para sanitizar
        max_length: Tamanho máximo (None = sem limite)
    
    Returns:
        String sanitizada
    """
    # Remove espaços extras
    text = " ".join(text.split())
    
    # Remove caracteres especiais perigosos
    text = re.sub(r'[<>{}[\]\\]', '', text)
    
    # Limita tamanho
    if max_length:
        text = text[:max_length]
    
    return text.strip()


def normalize_registration(registration: str) -> str:
    """
    Normaliza número de matrícula
    
    Args:
        registration: Matrícula para normalizar
    
    Returns:
        Matrícula normalizada
    """
    # Remove caracteres não numéricos
    normalized = re.sub(r'\D', '', registration)
    
    # Preenche com zeros à esquerda se necessário
    if len(normalized) < 6:
        normalized = normalized.zfill(6)
    
    return normalized


def mask_sensitive_data(data: str, visible_chars: int = 4) -> str:
    """
    Mascara dados sensíveis
    
    Args:
        data: Dado a mascarar
        visible_chars: Quantos caracteres manter visíveis
    
    Returns:
        String mascarada
    
    Example:
        >>> mask_sensitive_data("123456789", 4)
        "*****6789"
    """
    if len(data) <= visible_chars:
        return data
    
    masked_length = len(data) - visible_chars
    return "*" * masked_length + data[-visible_chars:]


# ==================== Validation Helpers ====================

def validate_email(email: str) -> bool:
    """
    Valida formato de email
    
    Args:
        email: Email para validar
    
    Returns:
        True se válido
    """
    pattern = r'^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$'
    return bool(re.match(pattern, email))


def validate_phone(phone: str) -> bool:
    """
    Valida número de telefone brasileiro
    
    Args:
        phone: Telefone para validar
    
    Returns:
        True se válido
    """
    # Remove caracteres não numéricos
    digits = re.sub(r'\D', '', phone)
    
    # Valida tamanho (10 ou 11 dígitos)
    return len(digits) in [10, 11]


def validate_cpf(cpf: str) -> bool:
    """
    Valida CPF brasileiro
    
    Args:
        cpf: CPF para validar
    
    Returns:
        True se válido
    """
    # Remove caracteres não numéricos
    cpf = re.sub(r'\D', '', cpf)
    
    # Verifica tamanho
    if len(cpf) != 11:
        return False
    
    # Verifica sequências inválidas
    if cpf == cpf[0] * 11:
        return False
    
    # Calcula primeiro dígito verificador
    sum_digits = sum(int(cpf[i]) * (10 - i) for i in range(9))
    digit1 = 11 - (sum_digits % 11)
    digit1 = 0 if digit1 > 9 else digit1
    
    if int(cpf[9]) != digit1:
        return False
    
    # Calcula segundo dígito verificador
    sum_digits = sum(int(cpf[i]) * (11 - i) for i in range(10))
    digit2 = 11 - (sum_digits % 11)
    digit2 = 0 if digit2 > 9 else digit2
    
    return int(cpf[10]) == digit2


def validate_card_number(card_number: Union[str, int]) -> bool:
    """
    Valida número de cartão
    
    Args:
        card_number: Número do cartão
    
    Returns:
        True se válido
    """
    card_str = str(card_number)
    
    # Remove espaços e hífens
    card_str = re.sub(r'[\s-]', '', card_str)
    
    # Verifica se contém apenas dígitos
    if not card_str.isdigit():
        return False
    
    # Verifica tamanho (mínimo 6, máximo 19 dígitos)
    return 6 <= len(card_str) <= 19


# ==================== Image Helpers ====================

def validate_base64_image(base64_string: str) -> Dict[str, Any]:
    """
    Valida string base64 de imagem
    
    Args:
        base64_string: String base64
    
    Returns:
        Dict com validação e informações
    """
    result = {
        "valid": False,
        "format": None,
        "size": 0,
        "errors": []
    }
    
    try:
        # Tenta decodificar
        image_data = base64.b64decode(base64_string)
        result["size"] = len(image_data)
        
        # Verifica formato pela assinatura (magic bytes)
        if image_data.startswith(b'\xff\xd8\xff'):
            result["format"] = "JPEG"
        elif image_data.startswith(b'\x89PNG'):
            result["format"] = "PNG"
        elif image_data.startswith(b'GIF89a') or image_data.startswith(b'GIF87a'):
            result["format"] = "GIF"
        else:
            result["errors"].append("Formato de imagem não suportado")
            return result
        
        # Verifica tamanho (máximo 5MB)
        max_size = 5 * 1024 * 1024
        if result["size"] > max_size:
            result["errors"].append(f"Imagem muito grande (máx {max_size / 1024 / 1024}MB)")
            return result
        
        result["valid"] = True
        
    except Exception as e:
        result["errors"].append(f"Erro ao decodificar base64: {str(e)}")
    
    return result


def resize_image_base64(
    base64_string: str,
    max_width: int = 800,
    max_height: int = 600
) -> Optional[str]:
    """
    Redimensiona imagem em base64 (requer PIL/Pillow)
    
    Args:
        base64_string: Imagem em base64
        max_width: Largura máxima
        max_height: Altura máxima
    
    Returns:
        Nova string base64 ou None se erro
    """
    try:
        from PIL import Image
        from io import BytesIO
        
        # Decodifica
        image_data = base64.b64decode(base64_string)
        image = Image.open(BytesIO(image_data))
        
        # Redimensiona mantendo aspect ratio
        image.thumbnail((max_width, max_height), Image.Resampling.LANCZOS)
        
        # Converte de volta para base64
        buffer = BytesIO()
        image.save(buffer, format=image.format or "JPEG")
        resized_data = buffer.getvalue()
        
        return base64.b64encode(resized_data).decode('utf-8')
        
    except ImportError:
        logger.warning("PIL/Pillow não instalado. Redimensionamento não disponível.")
        return None
    except Exception as e:
        logger.error(f"Erro ao redimensionar imagem: {e}")
        return None


# ==================== Security Helpers ====================

def generate_secure_token(length: int = 32) -> str:
    """
    Gera token seguro
    
    Args:
        length: Tamanho do token
    
    Returns:
        Token hexadecimal
    """
    return secrets.token_hex(length)


def hash_password(password: str, salt: Optional[str] = None) -> Dict[str, str]:
    """
    Cria hash de senha com salt
    
    Args:
        password: Senha para hash
        salt: Salt (gerado se None)
    
    Returns:
        Dict com hash e salt
    """
    if salt is None:
        salt = secrets.token_hex(16)
    
    hashed = hashlib.sha256(f"{password}{salt}".encode()).hexdigest()
    
    return {
        "hash": hashed,
        "salt": salt
    }


def verify_password(password: str, hashed: str, salt: str) -> bool:
    """
    Verifica senha contra hash
    
    Args:
        password: Senha para verificar
        hashed: Hash armazenado
        salt: Salt usado
    
    Returns:
        True se senha correta
    """
    check_hash = hashlib.sha256(f"{password}{salt}".encode()).hexdigest()
    return check_hash == hashed


def generate_random_password(
    length: int = 12,
    include_special: bool = True
) -> str:
    """
    Gera senha aleatória
    
    Args:
        length: Tamanho da senha
        include_special: Incluir caracteres especiais
    
    Returns:
        Senha gerada
    """
    characters = string.ascii_letters + string.digits
    
    if include_special:
        characters += "!@#$%&*"
    
    password = ''.join(secrets.choice(characters) for _ in range(length))
    
    return password


# ==================== Number Helpers ====================

def format_card_number(card_number: Union[str, int]) -> str:
    """
    Formata número de cartão com espaços
    
    Args:
        card_number: Número do cartão
    
    Returns:
        Número formatado
    
    Example:
        >>> format_card_number("1234567890123456")
        "1234 5678 9012 3456"
    """
    card_str = str(card_number).replace(" ", "")
    
    # Adiciona espaço a cada 4 dígitos
    formatted = " ".join([card_str[i:i+4] for i in range(0, len(card_str), 4)])
    
    return formatted


def format_file_size(size_bytes: int) -> str:
    """
    Formata tamanho de arquivo
    
    Args:
        size_bytes: Tamanho em bytes
    
    Returns:
        String formatada (ex: "1.5 MB")
    """
    for unit in ['B', 'KB', 'MB', 'GB']:
        if size_bytes < 1024.0:
            return f"{size_bytes:.2f} {unit}"
        size_bytes /= 1024.0
    
    return f"{size_bytes:.2f} TB"


def calculate_percentage(part: float, total: float, decimals: int = 2) -> float:
    """
    Calcula percentual
    
    Args:
        part: Parte
        total: Total
        decimals: Casas decimais
    
    Returns:
        Percentual
    """
    if total == 0:
        return 0.0
    
    return round((part / total) * 100, decimals)


# ==================== List & Dict Helpers ====================

def chunk_list(lst: List[Any], chunk_size: int) -> List[List[Any]]:
    """
    Divide lista em chunks
    
    Args:
        lst: Lista para dividir
        chunk_size: Tamanho de cada chunk
    
    Returns:
        Lista de chunks
    
    Example:
        >>> chunk_list([1,2,3,4,5], 2)
        [[1,2], [3,4], [5]]
    """
    return [lst[i:i + chunk_size] for i in range(0, len(lst), chunk_size)]


def flatten_dict(d: Dict, parent_key: str = '', sep: str = '.') -> Dict:
    """
    Achata dicionário aninhado
    
    Args:
        d: Dicionário para achatar
        parent_key: Chave pai
        sep: Separador
    
    Returns:
        Dicionário achatado
    
    Example:
        >>> flatten_dict({"a": {"b": 1, "c": 2}})
        {"a.b": 1, "a.c": 2}
    """
    items = []
    for k, v in d.items():
        new_key = f"{parent_key}{sep}{k}" if parent_key else k
        if isinstance(v, dict):
            items.extend(flatten_dict(v, new_key, sep=sep).items())
        else:
            items.append((new_key, v))
    return dict(items)


def remove_none_values(d: Dict) -> Dict:
    """
    Remove valores None de dicionário
    
    Args:
        d: Dicionário
    
    Returns:
        Dicionário sem None
    """
    return {k: v for k, v in d.items() if v is not None}


# ==================== Error Handling ====================

def safe_execute(func, default=None, log_error: bool = True):
    """
    Decorator para execução segura de funções
    
    Args:
        func: Função a executar
        default: Valor padrão em caso de erro
        log_error: Se deve logar erro
    
    Returns:
        Decorator
    """
    @wraps(func)
    def wrapper(*args, **kwargs):
        try:
            return func(*args, **kwargs)
        except Exception as e:
            if log_error:
                logger.error(f"Erro em {func.__name__}: {e}")
            return default
    
    return wrapper


# ==================== Logging Helpers ====================

def log_execution_time(func):
    """
    Decorator para logar tempo de execução
    """
    @wraps(func)
    async def async_wrapper(*args, **kwargs):
        start = datetime.now()
        result = await func(*args, **kwargs)
        duration = (datetime.now() - start).total_seconds()
        logger.info(f"{func.__name__} executado em {duration:.2f}s")
        return result
    
    @wraps(func)
    def sync_wrapper(*args, **kwargs):
        start = datetime.now()
        result = func(*args, **kwargs)
        duration = (datetime.now() - start).total_seconds()
        logger.info(f"{func.__name__} executado em {duration:.2f}s")
        return result
    
    import asyncio
    if asyncio.iscoroutinefunction(func):
        return async_wrapper
    return sync_wrapper


# ==================== Pagination Helpers ====================

def paginate_results(
    items: List[Any],
    page: int = 1,
    per_page: int = 20
) -> Dict[str, Any]:
    """
    Pagina lista de resultados
    
    Args:
        items: Lista de itens
        page: Número da página (começa em 1)
        per_page: Itens por página
    
    Returns:
        Dict com dados paginados
    """
    total = len(items)
    total_pages = (total + per_page - 1) // per_page
    
    start = (page - 1) * per_page
    end = start + per_page
    
    return {
        "items": items[start:end],
        "pagination": {
            "page": page,
            "per_page": per_page,
            "total": total,
            "total_pages": total_pages,
            "has_next": page < total_pages,
            "has_prev": page > 1
        }
    }