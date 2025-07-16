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

        masks: list[str] = (
            pl.read_parquet(index)
            .filter(
                pl.col("datatype") == "anat",
                pl.col("desc") == "brain",
                pl.col("res").is_null(),
            )
            .with_columns(masks=pl.col("root") + "/" + pl.col("path"))
            .select("masks")
            .to_series()
            .to_list()
        )

        anats = [x.replace("desc-brain_mask", "T1w") for x in masks]

        for mask, anat in zip(masks, anats):
            logging.info(f"{mask=}")
            mask_nii = nb.nifti1.Nifti1Image.load(mask)
            file_nii = nb.nifti1.Nifti1Image.load(anat)
            file1 = Path(mask).name
            for display_mode in models.DisplayMode.choices:
                logging.info(f"{display_mode=}")
                for cut in range(_private.N_CUTS):
                    logging.info(f"{cut=}")
                    if models.Image.objects.filter(
                        slice=cut,
                        display=display_mode[0],
                        step=models.Step.MASK,
                        file1=file1,
                    ).exists():
                        logging.info("Found object. Skipping")
                        continue

                    i = _private.get_mask(
                        cut=cut,
                        display_mode=models.DisplayMode(display_mode[0]),
                        mask_nii=mask_nii,
                        file_nii=file_nii,
                    )
                    models.Image.objects.create(
                        img=i,
                        slice=cut,
                        display=display_mode[0],
                        step=models.Step.MASK,
                        file1=file1,
                        file2=Path(anat).name,
                    )
