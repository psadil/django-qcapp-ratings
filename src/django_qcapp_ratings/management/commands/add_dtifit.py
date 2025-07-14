import asyncio
import logging
import typing as t
from pathlib import Path

import nibabel as nb
import typer
from django_typer.completers import path
from django_typer.management import TyperCommand

from django_qcapp_ratings import models

from . import _private


class Command(TyperCommand):
    def handle(
        self,
        subjects_dir: t.Annotated[
            Path,
            typer.Argument(
                file_okay=False,
                exists=True,
                dir_okay=True,
                readable=True,
                shell_complete=path.paths,
            ),
        ],
    ):
        """
        Add surface localization figures
        """

        for fa in subjects_dir.rglob("*dwi_FA.nii.gz"):
            logging.info(f"{fa=}")
            if models.Image.objects.filter(
                display=models.DisplayMode.Z, step=models.Step.DTIFIT, file1=fa.name
            ).exists():
                logging.info("Found object. Skipping")
                continue

            i = _private.get_dtifit(
                nii=nb.nifti1.Nifti1Image.load(fa),
                v1=nb.nifti1.Nifti1Image.load(
                    fa.with_name(fa.name.replace("FA", "V1"))
                ),
                v2=nb.nifti1.Nifti1Image.load(
                    fa.with_name(fa.name.replace("FA", "V2"))
                ),
                v3=nb.nifti1.Nifti1Image.load(
                    fa.with_name(fa.name.replace("FA", "V3"))
                ),
            )
            asyncio.run(
                models.Image.objects.acreate(
                    img=i,
                    display=models.DisplayMode.Z,
                    step=models.Step.DTIFIT,
                    file1=fa.name,
                )
            )
