from typing import Any, Callable, Dict, TypeAlias
from numpy.typing import NDArray
import numpy as np

NDArrayFloat: TypeAlias = NDArray[np.float64]
ConstraintDict: TypeAlias = Dict[str, Any]
MinimizerFn: TypeAlias = Callable[..., Any]
