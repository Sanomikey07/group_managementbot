from dataclasses import dataclass
from utils.security import RateLimiter


@dataclass
class AppContext:
    app: object
    db: object
    settings: object
    rate_limiter: RateLimiter
