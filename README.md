# Bot Control UI (strategy picker)

Цель:
- GET /arena максимум 1 раз в секунду (tick_sec=1.0)
- POST /move максимум 1 раз в секунду (только если есть команды)
- общий RPS ограничен 2.0 и дополнительно разнесён по времени (min interval 0.5s)

## Install
pip install -U fastapi uvicorn requests

## Run
python main.py --gui-host 127.0.0.1 --gui-port 8000 --tick-sec 1.0

Open: http://127.0.0.1:8000

## Endpoints
- GET /api/state — отдаёт кешированное состояние арены (полезно для твоего отдельного сервиса карты)
- GET/POST /api/control — пауза и tick_sec
- GET/POST /api/control/assignments — назначение стратегии бомберу
- GET/POST /api/control/default — дефолтная стратегия
- GET /api/control/strategies — список доступных стратегий

## Add a strategy
Просто создай файл `strategies/my_strategy.py` и класс:

```python
from dataclasses import dataclass
from typing import Optional
from model import Bomber
from strategies.base import DecisionContext, UnitPlan

@dataclass
class MyStrategy:
    id: str = "my_strategy"
    def decide_for_unit(self, unit: Bomber, ctx: DecisionContext) -> Optional[UnitPlan]:
        return None
```

Ничего в main.py менять не нужно — стратегия подхватится авто-дискавери.
