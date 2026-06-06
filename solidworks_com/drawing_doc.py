from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

from .errors import SolidWorksError
from .model import ModelDoc

logger = logging.getLogger(__name__)


class DrawingDoc(ModelDoc):
    """SOLIDWORKS Drawing document wrapper."""

    def insert_model_view(
        self,
        model_path: str | Path,
        *,
        view_type: str = 'front',
        x: float = 0.0,
        y: float = 0.0,
        scale: float = 1.0,
    ) -> Any:
        """Insert a model view into the drawing.

        Uses InsertModelInPrefPosition or CreateDrawView depending on
        the SOLIDWORKS version available.
        """
        path = str(Path(model_path).resolve())
        # Attempt CreateDrawView (newer API)
        try:
            view = self.com.CreateDrawView(
                path,  # model name
                float(x),  # X
                float(y),  # Y
                float(scale),  # scale
            )
            if view is not None:
                return view
        except (AttributeError, TypeError) as e:
            logger.debug("operation failed: %s", e)
        # Fallback to InsertModelInPrefPosition
        try:
            view = self.com.InsertModelInPrefPosition(path)
            if view is not None:
                return view
        except (AttributeError, TypeError) as e:
            logger.debug("operation failed: %s", e)
        raise SolidWorksError(f'Failed to insert model view: {path}')

    def add_dimension(
        self,
        entity_a: str,
        entity_b: str,
        value: float,
        *,
        dim_type: str = 'linear',
    ) -> Any:
        """Add a dimension between two named entities.

        .. note::
            Not implemented. SOLIDWORKS drawing dimensions require the entities
            to be pre-selected and then ``AddDimension2`` called with the
            correct selection marks. Use raw COM access for production work::

                self.com.ClearSelection2(True)
                self.com.Extension.SelectByID2(entity_a, "EDGE", 0, 0, 0, False, 1, None, 0)
                self.com.Extension.SelectByID2(entity_b, "EDGE", 0, 0, 0, True, 2, None, 0)
                dim = self.com.AddDimension2(x, y, 0)
        """
        raise NotImplementedError(
            "DrawingDoc.add_dimension is not implemented. "
            "Use self.com.AddDimension2 with pre-selected entities instead."
        )

    def add_sheet(self, name: str = 'Sheet2') -> Any:
        """Add a new sheet to the drawing."""
        try:
            sheet = self.com.NewSheet3(
                str(name),  # name
                12,  # paper size (A4)
                1.0,  # scale1
                1.0,  # scale2
                True,  # first angle
                0,  # template
            )
            return sheet
        except (AttributeError, TypeError) as e:
            logger.debug("add_sheet failed: %s", e)
        return None
