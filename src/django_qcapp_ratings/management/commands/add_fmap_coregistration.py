import asyncio
import json
import logging
import typing as t
from pathlib import Path

import nibabel as nb
import polars as pl
import typer
from django_typer.completers import path
from django_typer.management import TyperCommand

from django_qcapp_ratings import models

from . import _private


class Command(TyperCommand):
    def handle(
        self,
        index: t.Annotated[
            Path,
            typer.Argument(
                file_okay=True,
                exists=True,
                dir_okay=False,
                readable=True,
                shell_complete=path.paths,
            ),
        ],
    ):
        """
        Add Masks from BIDS Table
        """

        fieldmaps = pl.read_parquet(index).filter(
            pl.col("datatype") == "fmap", pl.col("desc") == "preproc"
        )

        for fieldmap in fieldmaps.iter_rows(named=True):
            logging.info(f"{fieldmap=}")
            root = Path(fieldmap.get("root", ""))
            path: str = fieldmap.get("path", "")
            sidecar: dict = json.loads(
                (root / path.replace(".nii.gz", ".json")).read_text()
            )
            file2 = root / path.replace("preproc", "epi")
            file2_nii = nb.nifti1.Nifti1Image.load(file2)
            intendedfor: list[str] = sidecar.get("IntendedFor")  # type:ignore
            for i in intendedfor:
                logging.info(f"{i=}")
                mask = (
                    root
                    / f"sub-{fieldmap.get('sub')}"
                    / i.replace("_bold", "_desc-brain_mask")
                )
                boldref = (
                    root
                    / f"sub-{fieldmap.get('sub')}"
                    / i.replace("_bold", "_desc-coreg_boldref")
                )

                mask_nii = nb.nifti1.Nifti1Image.load(mask)
                file_nii = nb.nifti1.Nifti1Image.load(boldref)
                file1 = boldref.name
                for display_mode in models.DisplayMode.choices:
                    logging.info(f"{display_mode=}")
                    for cut in range(_private.N_CUTS):
                        logging.info(f"{cut=}")
                        if models.Image.objects.filter(
                            slice=cut,
                            display=display_mode[0],
                            step=models.Step.FMAP_COREGISTRATION,
                            file1=file1,
                        ).exists():
                            logging.info("Found object. Skipping")
                            continue

                        i = _private.get_fmap_coregistration(
                            cut=cut,
                            display_mode=models.DisplayMode(display_mode[0]),
                            mask_nii=mask_nii,
                            file_nii=file_nii,
                            file2_nii=file2_nii,
                        )
                        asyncio.run(
                            models.Image.objects.acreate(
                                img=i,
                                slice=cut,
                                display=display_mode[0],
                                step=models.Step.FMAP_COREGISTRATION,
                                file1=file1,
                                file2=file2.name,
                            )
                        )
