# -*- coding: utf-8 -*-

import numpy as np
from dipy.io.stateful_tractogram import StatefulTractogram
from dipy.tracking.streamlinespeed import set_number_of_points, length

from scilpy.tractograms.uncompress import uncompress

from scilpy.image.utils import split_mask_blobs_kmeans
from scilpy.tractograms.streamline_operations import \
    filter_streamlines_by_length, compute_streamline_segment


def get_endpoints_density_map(streamlines, dimensions, point_to_select=1):
    """
    Compute an endpoints density map, supports selecting more than one points
    at each end.
    Parameters
    ----------
    streamlines: list of np.ndarray
        The list of streamlines to compute endpoints density from.
    dimensions: tuple
        The shape of the reference volume for the streamlines.
    point_to_select: int
        Instead of computing the density based on the first and last points,
        select more than one at each end. To support compressed streamlines,
        a resampling to 0.5mm per segment is performed.
    Returns
    -------
    np.ndarray: A np.ndarray where voxel values represent the density of
    endpoints.
    """
    endpoints_map_head, endpoints_map_tail = \
        get_head_tail_density_maps(streamlines, dimensions, point_to_select)
    return endpoints_map_head + endpoints_map_tail


def get_head_tail_density_maps(streamlines, dimensions, point_to_select=1):
    """
    Compute two separate endpoints density maps for the head and tail of
    a list of streamlines.

    Parameters
    ----------
    streamlines: list of np.ndarray
        The list of streamlines to compute endpoints density from.
    dimensions: tuple
        The shape of the reference volume for the streamlines.
    point_to_select: int
        Instead of computing the density based on the first and last points,
        select more than one at each end. To support compressed streamlines,
        a resampling to 0.5mm per segment is performed.
    Returns
    -------
    A tuple containing
        np.ndarray: A np.ndarray where voxel values represent the density of
            head endpoints.
        np.ndarray: A np.ndarray where voxel values represent the density of
            tail endpoints.
    """
    endpoints_map_head = np.zeros(dimensions)
    endpoints_map_tail = np.zeros(dimensions)
    for streamline in streamlines:
        # TODO: There is a bug here, the number of points is at max 2
        # meaning we can never select more than the first and last points
        nb_point = max(2,  int(length(streamline))*2)
        streamline = set_number_of_points(streamline, nb_point)
        points_list_head = \
            list(streamline[0:point_to_select, :])
        points_list_tail = \
            list(streamline[-point_to_select:, :])
        for xyz in points_list_head:
            x_val = np.clip(xyz[0], 0, dimensions[0]-1).astype(int)
            y_val = np.clip(xyz[1], 0, dimensions[1]-1).astype(int)
            z_val = np.clip(xyz[2], 0, dimensions[2]-1).astype(int)
            endpoints_map_head[x_val, y_val, z_val] += 1
        for xyz in points_list_tail:
            x_val = np.clip(xyz[0], 0, dimensions[0]-1).astype(int)
            y_val = np.clip(xyz[1], 0, dimensions[1]-1).astype(int)
            z_val = np.clip(xyz[2], 0, dimensions[2]-1).astype(int)
            endpoints_map_tail[x_val, y_val, z_val] += 1
    return endpoints_map_head, endpoints_map_tail


def cut_outside_of_mask_streamlines(sft, binary_mask, min_len=0):
    """ Cut streamlines so their longest segment are within the bounding box
    or a binary mask.
    This function erases the data_per_point and data_per_streamline.

    Parameters
    ----------
    sft: StatefulTractogram
        The sft to cut streamlines (using a single mask with 1 entity) from.
    binary_mask: np.ndarray
        Boolean array representing the region (must contain 1 entity)
    min_len: float
        Minimum length from the resulting streamlines.

    Returns
    -------
    new_sft : StatefulTractogram
        New object with the streamlines trimmed within the mask.
    """
    sft.to_vox()
    sft.to_corner()
    streamlines = sft.streamlines

    # TODO: This function can be uniformized with cut_between_masks_streamlines
    # TODO: It can also be optimized and simplified

    new_streamlines = []
    for _, streamline in enumerate(streamlines):
        entry_found = False
        last_success = 0
        curr_len = 0
        longest_seq = (0, 0)
        # For each point in the streamline, find the longest sequence of points
        # that are in the mask.
        for ind, pos in enumerate(streamline):
            pos = tuple(pos.astype(np.int16))
            if binary_mask[pos]:
                if not entry_found:
                    entry_found = True
                    last_success = ind
                    curr_len = 0
                else:
                    curr_len += 1
                    if curr_len > longest_seq[1] - longest_seq[0]:
                        longest_seq = (last_success, ind + 1)
            else:
                if entry_found:
                    entry_found = False
                    if curr_len > longest_seq[1] - longest_seq[0]:
                        longest_seq = (last_success, ind)
                        curr_len = 0

        if longest_seq[1] != 0:
            new_streamlines.append(streamline[longest_seq[0]:longest_seq[1]])

    new_sft = StatefulTractogram.from_sft(new_streamlines, sft)
    return filter_streamlines_by_length(new_sft, min_length=min_len)


def cut_between_masks_streamlines(sft, binary_mask, min_len=0):
    """ Cut streamlines so their segment are within the bounding box
    or going from binary mask #1 to binary mask #2.
    This function erases the data_per_point and data_per_streamline.

    Parameters
    ----------
    sft: StatefulTractogram
        The sft to cut streamlines (using a single mask with 2 entities) from.
    binary_mask: np.ndarray
        Boolean array representing the region (must contain 2 entities)
    min_len: float
        Minimum length from the resulting streamlines.
    Returns
    -------
    new_sft : StatefulTractogram
        New object with the streamlines trimmed within the masks.
    """
    sft.to_vox()
    sft.to_corner()
    streamlines = sft.streamlines

    density = get_endpoints_density_map(streamlines, binary_mask.shape)
    density[density > 0] = 1
    density[binary_mask == 0] = 0

    # Split head and tail from mask
    roi_data_1, roi_data_2 = split_mask_blobs_kmeans(
        binary_mask, nb_clusters=2)

    new_streamlines = []
    # Get the indices of the "voxels" intersected by the streamlines and the
    # mapping from points to indices.
    (indices, points_to_idx) = uncompress(streamlines, return_mapping=True)

    for strl_idx, strl in enumerate(streamlines):
        # The "voxels" intersected by the current streamline
        strl_indices = indices[strl_idx]
        # Find the first and last "voxels" of the streamline that are in the
        # ROIs
        in_strl_idx, out_strl_idx = _intersects_two_rois(roi_data_1,
                                                         roi_data_2,
                                                         strl_indices)
        # If the streamline intersects both ROIs
        if in_strl_idx is not None and out_strl_idx is not None:
            points_to_indices = points_to_idx[strl_idx]
            # Compute the new streamline by keeping only the segment between
            # the two ROIs
            cut_strl = compute_streamline_segment(strl, strl_indices,
                                                  in_strl_idx, out_strl_idx,
                                                  points_to_indices)
            # Add the new streamline to the sft
            new_streamlines.append(cut_strl)

    new_sft = StatefulTractogram.from_sft(new_streamlines, sft)
    return filter_streamlines_by_length(new_sft, min_length=min_len)


def _intersects_two_rois(roi_data_1, roi_data_2, strl_indices):
    """ Find the first and last points of the streamline that are in the ROIs.

    Parameters
    ----------
    roi_data_1: np.ndarray
        Boolean array representing the region #1
    roi_data_2: np.ndarray
        Boolean array representing the region #2
    strl_indices: list of tuple (N, 3)
        3D indices of the voxels intersected by the streamline

    Returns
    -------
    in_strl_idx : int
        index of the first point (of the streamline) to be in the masks
    out_strl_idx : int
        index of the last point (of the streamline) to be in the masks
    """

    entry_found = False
    exit_found = False
    went_out_of_exit = False
    exit_roi_data = None
    in_strl_idx = None
    out_strl_idx = None

    # TODO: This function can be simplified and optimized

    for idx, point in enumerate(strl_indices):
        if entry_found and exit_found:
            # Still add points that are in exit roi, to mimic entry ROI
            # This will need to be modified to correctly handle continuation
            if exit_roi_data[tuple(point)] > 0:
                if not went_out_of_exit:
                    out_strl_idx = idx
            else:
                went_out_of_exit = True
        elif entry_found and not exit_found:
            # If we reached the exit ROI
            if exit_roi_data[tuple(point)] > 0:
                exit_found = True
                out_strl_idx = idx
        elif not entry_found:
            # Check if we are in one of ROIs
            if roi_data_1[tuple(point)] > 0 or roi_data_2[tuple(point)] > 0:
                entry_found = True
                in_strl_idx = idx
                if roi_data_1[tuple(point)] > 0:
                    exit_roi_data = roi_data_2
                else:
                    exit_roi_data = roi_data_1

    return in_strl_idx, out_strl_idx
