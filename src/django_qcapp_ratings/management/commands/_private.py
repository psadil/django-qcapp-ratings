import io
import logging
import typing
import zlib
from pathlib import Path

import nibabel as nb
import numpy as np
import polars as pl
from matplotlib import pyplot as plt
from nilearn import image, plotting
from nilearn.plotting import displays

from django_qcapp_ratings import datasets, models

N_CUTS = 7
SPATIAL_NORMALIZATION_CUTS = {
    "x": {0: -50, 1: 5, 2: 30},
    "y": {0: -65, 1: 20, 2: 54},
    "z": {0: -6, 1: 13, 2: 58},
}


def cuts_from_bbox(
    mask_nii: nb.nifti1.Nifti1Image, cuts: int = 7
) -> dict[models.DisplayMode, list[float]]:
    """Find equi-spaced cuts for presenting images."""
    if mask_nii.affine is None:
        raise ValueError("nifti must have affine")
    mask_data = np.asanyarray(mask_nii.dataobj) > 0.0

    # First, project the number of masked voxels on each axes
    ijk_counts = [
        mask_data.sum(2).sum(1),  # project sagittal planes to transverse (i) axis
        mask_data.sum(2).sum(0),  # project coronal planes to to longitudinal (j) axis
        mask_data.sum(1).sum(0),  # project axial planes to vertical (k) axis
    ]

    # If all voxels are masked in a slice (say that happens at k=10),
    # then the value for ijk_counts for the projection to k (ie. ijk_counts[2])
    # at that element of the orthogonal axes (ijk_counts[2][10]) is
    # the total number of voxels in that slice (ie. Ni x Nj).
    # Here we define some thresholds to consider the plane as "masked"
    # The thresholds vary because of the shape of the brain
    # I have manually found that for the axial view requiring 30%
    # of the slice elements to be masked drops almost empty boxes
    # in the mosaic of axial planes (and also addresses #281)
    ijk_th = np.ceil(
        [
            (mask_data.shape[1] * mask_data.shape[2]) * 0.2,  # sagittal
            (mask_data.shape[0] * mask_data.shape[2]) * 0.1,  # coronal
            (mask_data.shape[0] * mask_data.shape[1]) * 0.3,  # axial
        ]
    ).astype(int)

    vox_coords = np.zeros((4, cuts), dtype=np.float32)
    vox_coords[-1, :] = 1.0
    for ax, (c, th) in enumerate(zip(ijk_counts, ijk_th)):
        # Start with full plane if mask is seemingly empty
        smin, smax = (0, mask_data.shape[ax] - 1)

        B = np.argwhere(c > th)
        if B.size < cuts:  # Threshold too high
            B = np.argwhere(c > 0)
        if B.size:
            smin, smax = B.min(), B.max()

        vox_coords[ax, :] = np.linspace(smin, smax, num=cuts + 2)[1:-1]

    ras_coords = mask_nii.affine.dot(vox_coords)[:3, ...]
    return {
        k: list(v)
        for k, v in zip(
            [models.DisplayMode.X, models.DisplayMode.Y, models.DisplayMode.Z],
            np.around(ras_coords, 3),
        )
    }


def get_mask(
    cut: int,
    mask_nii: nb.nifti1.Nifti1Image,
    file_nii: nb.nifti1.Nifti1Image,
    display_mode: models.DisplayMode = models.DisplayMode(models.DisplayMode.X),
    figsize: tuple[float, float] = (6.4, 4.8),
) -> bytes:
    cuts = cuts_from_bbox(mask_nii, cuts=N_CUTS).get(display_mode)
    if cuts is None:
        raise ValueError("Misaglinged Display Mode")
    f = plt.figure(figsize=figsize, layout="none")
    with io.BytesIO() as img:
        p: displays.OrthoSlicer = plotting.plot_anat(
            file_nii,
            cut_coords=[cuts[cut]],
            display_mode=display_mode.name.lower(),
            figure=f,
            vmax=np.quantile(file_nii.get_fdata(), 0.95),
        )  # type: ignore
        try:
            p.add_contours(
                mask_nii, levels=[0.5], colors="g", filled=True, transparency=0.5
            )
        except ValueError:
            pass
        p.savefig(img)
        plt.close(f)
        return zlib.compress(img.getvalue())


def get_surface_localization(
    cut: int,
    brain_nii: nb.nifti1.Nifti1Image,
    ribbon_nii: nb.nifti1.Nifti1Image,
    display_mode: models.DisplayMode = models.DisplayMode(models.DisplayMode.X),
    figsize: tuple[float, float] = (6.4, 4.8),
    linewidths=0.5,
    levels: list[float] = [0.5],
) -> bytes:
    cuts = cuts_from_bbox(ribbon_nii, cuts=N_CUTS).get(display_mode)
    if cuts is None:
        raise ValueError("Misaglinged Display Mode")
    f = plt.figure(figsize=figsize, layout="none")
    contour_data = ribbon_nii.get_fdata() % 39
    white = image.new_img_like(ribbon_nii, contour_data == 2)
    pial = image.new_img_like(ribbon_nii, contour_data >= 2)
    with io.BytesIO() as img:
        p: displays.OrthoSlicer = plotting.plot_anat(
            brain_nii,
            cut_coords=[cuts[cut]],
            display_mode=display_mode.name.lower(),
            figure=f,
        )  # type: ignore
        try:
            p.add_contours(white, colors="b", linewidths=linewidths, levels=levels)
            p.add_contours(pial, colors="r", linewidths=linewidths, levels=levels)
        except ValueError:
            pass
        p.savefig(img)
        plt.close(f)
        return zlib.compress(img.getvalue())


def get_spatial_normalization(
    cut: int,
    file_nii: nb.nifti1.Nifti1Image,
    display_mode: models.DisplayMode,
    figsize: tuple[float, float] = (6.4, 4.8),
) -> bytes:
    if cut > 2:
        raise ValueError("Unknown cut")

    f = plt.figure(figsize=figsize, layout="none")
    with io.BytesIO() as img:
        p: displays.OrthoSlicer = plotting.plot_roi(
            roi_img=datasets.get_layout(),
            bg_img=file_nii,
            cut_coords=[SPATIAL_NORMALIZATION_CUTS[display_mode.name.lower()][cut]],
            display_mode=display_mode.name.lower(),
            figure=f,
        )  # type: ignore
        p.savefig(img)
        plt.close(f)
        return zlib.compress(img.getvalue())


def mgz_to_nifti(src) -> nb.nifti1.Nifti1Image:
    mgh = nb.freesurfer.mghformat.load(src)
    return nb.nifti1.Nifti1Image.from_image(mgh)


def merge_or_write_image_db(d: pl.LazyFrame, dst: Path) -> None:
    if dst.exists():
        logging.info(f"Using existing database {dst}")
        joined = (
            pl.scan_parquet(dst)
            .join(
                d,
                how="full",
                on=["slice", "file1", "file2", "display", "step"],
                coalesce=True,
            )
            .with_columns(match=pl.col("img") == pl.col("img_right"))
            .collect()
        )
        if joined.select("match").to_series().any():
            logging.warning("Replacing images")
            logging.debug(
                joined.filter(pl.col("match")).drop(
                    pl.selectors.starts_with("img"), "match"
                )
            )
        joined.drop("img_left").write_parquet(dst)
    else:
        d.sink_parquet(dst)


async def merge_imgs(imgs: typing.Sequence[models.Image]) -> None:
    if len(imgs):
        await models.Image.objects.abulk_create(
            imgs,
            update_conflicts=True,  # type: ignore
            update_fields=["img", "created"],
            unique_fields=["slice", "file1", "display", "step"],
        )
