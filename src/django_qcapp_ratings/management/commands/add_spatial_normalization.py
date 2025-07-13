import asyncio
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
        update: t.Annotated[
            bool, typer.Option(help="Whether to update img in database")
        ] = False,
    ):
        """
        Add surface localization figures
        """

        anats: list[str] = (
            pl.read_parquet(index)
            .filter(
                pl.col("datatype") == "anat",
                pl.col("desc") == "preproc",
                pl.col("res").is_null(),
                pl.col("space") == "MNI152NLin2009cAsym",
            )
            .with_columns(anat=pl.col("root") + "/" + pl.col("path"))
            .select("anat")
            .to_series()
            .to_list()
        )

        for anat in anats:
            logging.info(f"{anat=}")
            file_nii = nb.nifti1.Nifti1Image.load(anat)
            file1 = Path(anat).name
            for display_mode in models.DisplayMode.choices:
                logging.info(f"{display_mode=}")
                for cut in range(2):
                    logging.info(f"{cut=}")
                    if (
                        i := models.Image.objects.filter(
                            slice=cut,
                            display=display_mode[0],
                            step=models.Step.SPATIAL_NORMALIZATION,
                            file1=file1,
                        )
                    ).exists():
                        if not update:
                            logging.info("Found object. Skipping")
                            continue
                        else:
                            i.delete()
                    i = _private.get_spatial_normalization(
                        cut=cut,
                        display_mode=models.DisplayMode(display_mode[0]),
                        file_nii=file_nii,
                    )
                    asyncio.run(
                        models.Image.objects.acreate(
                            img=i,
                            slice=cut,
                            display=display_mode[0],
                            step=models.Step.SPATIAL_NORMALIZATION,
                            file1=file1,
                        )
                    )
