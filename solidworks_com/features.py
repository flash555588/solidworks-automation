from __future__ import annotations

from typing import Any

from .constants import ChamferOption, ChamferType, EndCondition, RefPlaneConstraint
from .errors import SolidWorksError
from .units import deg


class FeatureTools:
    def __init__(self, model: Any) -> None:
        self.model = model

    @property
    def com(self) -> Any:
        return self.model.com.FeatureManager

    def extrude_blind(
        self,
        depth: float,
        *,
        reverse: bool = False,
        merge: bool = True,
        thin_feature: bool = False,
        flip: bool = False,
    ) -> Any:
        """Create a blind extrusion from the active sketch.

        Args:
            depth: Extrusion depth in meters. Must be non-negative.
            reverse: If True, reverse the extrusion direction.
            merge: If True, merge with existing body.
            thin_feature: If True, create a thin feature.
            flip: If True, flip the extrusion direction.
        """
        if depth < 0:
            raise ValueError(f"extrude depth must be non-negative, got {depth}")
        feature = self.com.FeatureExtrusion3(
            True,                   # sd (single direction) - MUST be True
            bool(flip),             # flip
            bool(reverse),          # dir (reverse direction)
            int(EndCondition.Blind),  # end condition 1
            int(EndCondition.Blind),  # end condition 2
            float(depth),           # depth 1
            0.0,                    # depth 2
            False,                  # draft 1
            False,                  # draft 2
            False,                  # draft outward 1
            False,                  # draft outward 2
            0.0,                    # draft angle 1
            0.0,                    # draft angle 2
            False,                  # offset reverse 1
            False,                  # offset reverse 2
            False,                  # translate surface 1
            False,                  # translate surface 2
            bool(merge),            # merge
            True,                   # use feature scope
            True,                   # auto select
            int(EndCondition.Blind),  # end condition 2 type
            0.0,                    # offset distance 2
            False,                  # offset reverse 2
        )
        if feature is None:
            raise SolidWorksError("Failed to create blind extrusion")
        return feature

    def extrude_midplane(self, depth: float, *, merge: bool = True, thin_feature: bool = False) -> Any:
        """Create a mid-plane extrusion from the active sketch."""
        if depth < 0:
            raise ValueError(f"extrude depth must be non-negative, got {depth}")
        feature = self.com.FeatureExtrusion3(
            True,                   # sd (single direction) - MUST be True
            False,                  # flip
            False,
            int(EndCondition.MidPlane),
            int(EndCondition.Blind),
            float(depth),
            0.0,
            False,
            False,
            False,
            False,
            0.0,
            0.0,
            False,
            False,
            False,
            False,
            bool(merge),
            True,
            True,
            int(EndCondition.Blind),
            0.0,
            False,
        )
        if feature is None:
            raise SolidWorksError("Failed to create mid-plane extrusion")
        return feature

    def cut_blind(self, depth: float, *, reverse: bool = False, normal_cut: bool = False) -> Any:
        """Create a blind cut from the active sketch.

        The cut travels from the sketch plane in the sketch's **outward
        normal** direction by default (i.e. away from the viewer when
        looking straight at the sketch).  Pass ``reverse=True`` to flip
        the direction.

        Plane-specific defaults
        -----------------------
        ``Top Plane`` (XY plane, Z = 0):
            Default direction is **−Z** (downward / away from a body that
            sits above Z = 0).  To cut **into** a body above the plane use
            ``reverse=True``, or prefer :meth:`cut_midplane` with
            ``depth * 2`` which is direction-agnostic.

        ``Front Plane`` (XZ plane, Y = 0):
            Default direction is **−Y**.

        ``Right Plane`` (YZ plane, X = 0):
            Default direction is **−X**.

        When in doubt
        -------------
        Use :meth:`cut_midplane` — it cuts symmetrically about the sketch
        plane and will always intersect a body that straddles the plane::

            # Safe pattern for a bottom pocket on Top Plane
            part.select_plane("Top Plane")
            with part.sketch() as sk:
                sk.corner_rectangle(...)
            part.features.cut_midplane(pocket_depth * 2)
        """
        if depth < 0:
            raise ValueError(f"cut depth must be non-negative, got {depth}")
        feature = self.com.FeatureCut4(
            True,                   # sd (single direction) - MUST be True
            False,
            bool(reverse),
            int(EndCondition.Blind),
            int(EndCondition.Blind),
            float(depth),
            0.0,
            False,
            False,
            False,
            False,
            0.0,
            0.0,
            False,
            False,
            False,
            False,
            bool(normal_cut),
            True,
            True,
            False,
            True,
            False,
            int(EndCondition.Blind),
            0.0,
            False,
            True,
        )
        if feature is None:
            raise SolidWorksError("Failed to create blind cut")
        return feature

    def cut_midplane(self, depth: float, *, normal_cut: bool = False) -> Any:
        """Create a mid-plane cut from the active sketch."""
        if depth < 0:
            raise ValueError(f"cut depth must be non-negative, got {depth}")
        feature = self.com.FeatureCut4(
            True,                   # sd (single direction) - MUST be True
            False,                  # flip
            False,
            int(EndCondition.MidPlane),
            int(EndCondition.Blind),
            float(depth),
            0.0,
            False,
            False,
            False,
            False,
            0.0,
            0.0,
            False,
            False,
            False,
            False,
            bool(normal_cut),
            True,
            True,
            False,
            True,
            False,
            int(EndCondition.Blind),
            0.0,
            False,
            True,
        )
        if feature is None:
            raise SolidWorksError("Failed to create mid-plane cut")
        return feature

    def revolve(
        self, *, angle: float | None = None, cut: bool = False, reverse: bool = False, merge: bool = True
    ) -> Any:
        """Create a revolve feature from the active sketch.

        The sketch must contain a closed profile. The revolve axis is
        automatically selected from the sketch's first centerline or
        the Y-axis of the sketch plane.

        Args:
            angle: Revolve angle in degrees (default 360).
            cut: If True, create a cut revolve.
            reverse: If True, reverse the revolve direction.
            merge: If True, merge with existing body.
        """
        angle_rad = deg(angle) if angle is not None else deg(360)
        feature = self.com.FeatureRevolve2(
            True,           # Single direction
            False,          # Not both directions
            False,          # Not thin feature
            bool(cut),      # Cut
            bool(reverse),  # Reverse
            False,          # Not thin feature
            int(EndCondition.Blind),  # End condition 1
            int(EndCondition.Blind),  # End condition 2
            float(angle_rad),         # Angle 1 (radians)
            0.0,                      # Angle 2
            False,          # Offset reverse 1
            False,          # Offset reverse 2
            0.0,            # Offset 1
            0.0,            # Offset 2
            0,              # Thin type
            0.0,            # Thin thickness 1
            0.0,            # Thin thickness 2
            bool(merge),    # Merge
            True,           # Use feature scope
            True,           # Auto select
        )
        if feature is None:
            raise SolidWorksError("Failed to create revolve feature")
        return feature

    def bool_union(self, body1: Any, body2: Any) -> Any:
        # v0.2: boolean-add two bodies via InsertCombineFeature.
        # Select both bodies (mark=1) and call the feature manager.
        # The operation type 0 is swCombineOperationType_Add.
        self.model.clear_selection()
        self.model.select_object(body1, mark=1)
        self.model.select_object(body2, append=True, mark=1)
        feature = self.com.FeatureManager.InsertCombineFeature(
            0,  # swCombineOperationType_Add
            body1,
            body2,
        )
        if feature is None:
            raise SolidWorksError("Failed to create boolean union")
        return feature

    def fillet_selected(self, radius: float, *, options: int = 0) -> Any:
        if radius < 0:
            raise ValueError(f"fillet radius must be non-negative, got {radius}")
        feature = self.com.FeatureFillet3(
            int(options), float(radius), 0.0, 0.0, 0, 0, 0, None, None, None, None, None, None, None
        )
        if feature is None:
            raise SolidWorksError("Failed to create fillet from selected entities")
        return feature

    def chamfer_selected(
        self,
        distance: float,
        *,
        chamfer_type: int | ChamferType = ChamferType.EqualDistance,
        options: int | ChamferOption = ChamferOption.NONE,
        angle: float = deg(45),
        other_distance: float = 0.0,
        vertex_distance_1: float = 0.0,
        vertex_distance_2: float = 0.0,
        vertex_distance_3: float = 0.0,
    ) -> Any:
        """Create a chamfer from the current edge selection.

        Args:
            distance: Primary chamfer distance in meters.
            chamfer_type: One of :class:`ChamferType`. The default
                ``EqualDistance`` interprets ``distance`` as the
                single equal offset on both faces.
            options: Bitfield of :class:`ChamferOption`.
            angle: Chamfer angle in radians. Used only when
                ``chamfer_type`` is :attr:`ChamferType.AngleDistance`.
            other_distance: Secondary distance (used by
                :attr:`ChamferType.DistanceDistance`).
            vertex_distance_1/2/3: Per-vertex distances (used by
                :attr:`ChamferType.Vertex`).

        SOLIDWORKS' ``InsertFeatureChamfer`` API requires edges to be
        selected first (``Edge`` or ``Feature`` selection). After
        selecting the edges with the appropriate mark, call this
        method to commit the chamfer.
        """
        if distance < 0:
            raise ValueError(f"chamfer distance must be non-negative, got {distance}")
        feature = self.com.InsertFeatureChamfer(
            int(options),
            int(chamfer_type),
            float(distance),
            float(angle),
            float(other_distance),
            float(vertex_distance_1),
            float(vertex_distance_2),
            float(vertex_distance_3),
        )
        if feature is None:
            raise SolidWorksError("Failed to create chamfer from selected entities")
        return feature

    def circular_pattern_selected(
        self,
        instances: int,
        angle: float = deg(360),
        *,
        flip_direction: bool = False,
        direction_dimension_name: str = "",
        geometry_pattern: bool = True,
        equal_spacing: bool = True,
        vary_instance: bool = False,
    ) -> Any:
        """Create a circular pattern from the current ordered selection.

        SOLIDWORKS expects the rotation axis selected with mark 1 and seed
        features selected with mark 4 before this call.
        """
        feature = self.com.FeatureCircularPattern4(
            int(instances),
            float(angle),
            bool(flip_direction),
            str(direction_dimension_name),
            bool(geometry_pattern),
            bool(equal_spacing),
            bool(vary_instance),
        )
        if feature is None:
            raise SolidWorksError("Failed to create circular pattern from selected entities")
        return feature

    def loft_boss(
        self,
        *,
        closed: bool = False,
        keep_tangency: bool = True,
        force_non_rational: bool = False,
        tess_tolerance_factor: float = 1.0,
        start_matching_type: int = 0,
        end_matching_type: int = 0,
        start_tangent_length: float = 0.0,
        end_tangent_length: float = 0.0,
        start_tangent_dir: bool = False,
        end_tangent_dir: bool = False,
        merge: bool = True,
        guide_curve_influence: int = 0,
    ) -> Any:
        feature = self.com.InsertProtrusionBlend2(
            bool(closed),
            bool(keep_tangency),
            bool(force_non_rational),
            float(tess_tolerance_factor),
            int(start_matching_type),
            int(end_matching_type),
            float(start_tangent_length),
            float(end_tangent_length),
            bool(start_tangent_dir),
            bool(end_tangent_dir),
            False,
            0.0,
            0.0,
            0,
            bool(merge),
            True,
            True,
            int(guide_curve_influence),
        )
        if feature is None:
            raise SolidWorksError("Failed to create loft boss")
        return feature

    def loft_surface(
        self,
        *,
        closed: bool = False,
        keep_tangency: bool = True,
        force_non_rational: bool = False,
        tess_tolerance_factor: float = 1.0,
        start_matching_type: int = 0,
        end_matching_type: int = 0,
    ) -> Any:
        result = self.model.com.InsertLoftRefSurface2(
            bool(closed),
            bool(keep_tangency),
            bool(force_non_rational),
            float(tess_tolerance_factor),
            int(start_matching_type),
            int(end_matching_type),
        )
        if result is False:
            raise SolidWorksError("Failed to create loft surface")
        return result

    def loft_cut(
        self,
        *,
        keep_tangency: bool = True,
        force_non_rational: bool = False,
        tess_tolerance_factor: float = 1.0,
        start_matching_type: int = 0,
        end_matching_type: int = 0,
        merge: bool = True,
    ) -> Any:
        """Cut the active body using the active loft profile selections.
        The caller must have already selected 2+ profile sketches
        (with mark=1 each) using :pymeth:`select_object` before
        calling this method. ``merge`` controls whether the cut
        removes the cut volume from the active body (``True``) or
        produces a separate removed volume.
        """
        feature = self.com.InsertCutBlend(
            bool(keep_tangency),
            bool(force_non_rational),
            float(tess_tolerance_factor),
            int(start_matching_type),
            int(end_matching_type),
            bool(merge),
        )
        if feature is None:
            raise SolidWorksError("Failed to create loft cut")
        return feature

    def thicken_selected(
        self, thickness: float, *, direction: int = 0, fill_volume: bool = False, merge: bool = True
    ) -> Any:
        feature = self.com.FeatureBossThicken(
            float(thickness), int(direction), 0, bool(fill_volume), bool(merge), True, True
        )
        if feature is None:
            raise SolidWorksError("Failed to thicken selected surface")
        return feature

    def fill_surface_selected(self, *, resolution: int = 3) -> Any:
        feature = self.com.InsertFillSurface(int(resolution))
        if feature is None:
            raise SolidWorksError("Failed to create fill surface from selected boundary")
        return feature

    def knit_selected(
        self,
        *,
        try_to_form_solid: bool = True,
        merge_entities: bool = True,
        knit_tolerance: float = 0.00001,
        use_gap_filters: bool = False,
        max_gap: float = 0.0001,
    ) -> Any:
        feature = self.com.InsertSewRefSurface(
            bool(use_gap_filters),
            bool(try_to_form_solid),
            bool(merge_entities),
            float(knit_tolerance),
            float(max_gap),
        )
        if feature is None:
            raise SolidWorksError("Failed to knit selected surfaces")
        return feature

    def offset_plane(self, distance: float, *, flip: bool = False) -> Any:
        constraint = RefPlaneConstraint.Distance | (RefPlaneConstraint.OptionFlip if flip else RefPlaneConstraint.NONE)
        plane = self.com.InsertRefPlane(int(constraint), float(distance), 0, 0.0, 0, 0.0)
        if plane is None:
            raise SolidWorksError("Failed to create offset reference plane")
        return plane

    def mirror_selected(self, *, merge: bool = True) -> Any:
        """Mirror the current selection across a pre-selected plane.

        The caller must have selected the mirror plane (mark=1) and
        the seed features (mark=4) before calling this method.
        """
        feature = self.com.FeatureMirror3(
            2,  # n_instances (original + mirror)
            None,  # mirror_plane -- pre-selected
            None,  # features -- pre-selected
            bool(merge),
        )
        if feature is None:
            raise SolidWorksError('Failed to create mirror feature')
        return feature

    def linear_pattern_selected(self, count: int, spacing: float, *, merge: bool = True) -> Any:
        """Create a linear pattern from the current selection.

        The caller must have selected the direction reference (mark=1)
        and the seed features (mark=4) before calling this method.
        """
        feature = self.com.FeatureLinearPattern3(
            int(count),
            float(spacing),
            None,  # direction -- pre-selected
            None,  # features -- pre-selected
            bool(merge),
        )
        if feature is None:
            raise SolidWorksError('Failed to create linear pattern')
        return feature

    def shell_selected(self, thickness: float, *, remove_faces: bool = True) -> Any:
        """Shell the selected faces.

        The caller must have selected the faces to remove (mark=1)
        before calling this method.  If no faces are selected, the
        body is hollowed uniformly.
        """
        feature = self.com.InsertFeatureShell(
            float(thickness),
            bool(remove_faces),
        )
        if feature is None:
            raise SolidWorksError('Failed to create shell feature')
        return feature

    def draft_selected(
        self,
        angle: float,
        *,
        draft_type: int = 0,
    ) -> Any:
        """Create a draft on the selected faces.

        The caller must have selected the neutral plane (mark=1) and
        the faces to draft (mark=2) before calling this method.
        """
        feature = self.com.InsertFeatureDraft(
            int(draft_type),
            float(angle),
            None,  # direction -- pre-selected neutral plane
            None,  # faces -- pre-selected
        )
        if feature is None:
            raise SolidWorksError('Failed to create draft feature')
        return feature

    def call(self, name: str, *args: Any, require: bool = True) -> Any:
        result = getattr(self.com, name)(*args)
        if require and result is None:
            raise SolidWorksError(f"FeatureManager.{name} returned None")
        return result
