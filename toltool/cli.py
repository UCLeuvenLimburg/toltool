from collections import namedtuple
from zipfile import ZipFile
from typing import Iterable
from unidecode import unidecode
from io import BytesIO
import pydantic
import click
import sys
import os
import re


class MetadataError(Exception):
    pass


class Metadata(pydantic.BaseModel):
    name: str
    qid: str
    submitted_files: dict[str, str]


def process_command_line_arguments():
    cli()


@click.group()
def cli():
    ...


@cli.command()
@click.argument('archive', type=str)
def unpack(archive):
    with ZipFile(archive) as file:
        metadatas = extract_metadata_from_archive(file)

        for metadata in metadatas:
            process_submission(file, metadata)


def process_submission(archive: ZipFile, metadata: Metadata) -> None:
    directory = slug_from_name(metadata.name)

    if len(metadata.submitted_files) == 0:
        print(f'WARNING: {metadata.name} ({metadata.qid}) has submitted 0 files')

    if not os.path.exists(directory):
            os.mkdir(directory)

    for (filename_in_archive, target_filename) in metadata.submitted_files.items():
        extract_submission_file(
            archive=archive,
            filename_in_archive=filename_in_archive,
            target_filename=target_filename,
            directory=directory
        )


def extract_submission_file(archive: ZipFile, filename_in_archive: str, target_filename: str, directory: str) -> None:
    if target_filename.endswith('.zip'):
        extract_and_unpack_submission_file(archive, filename_in_archive, directory)
    else:
        extract(archive, filename_in_archive, target_filename, directory)


def extract_and_unpack_submission_file(archive: ZipFile, filename_in_archive: str, directory: str) -> None:
    buffer = BytesIO(archive.read(filename_in_archive))
    print(f'Extracting {filename_in_archive} to {directory}')
    with ZipFile(buffer, 'r') as submitted_file:
        submitted_file.extractall(directory)


def extract(archive: ZipFile, filename_in_archive: str, target_filename: str, directory: str):
    original_path = os.path.join('.', directory, filename_in_archive)
    target_path = os.path.join('.', directory, target_filename)
    print(f'Extracting {filename_in_archive} to {target_path}')
    archive.extract(filename_in_archive, directory)
    os.rename(original_path, target_path)


def slug_from_name(name: str) -> str:
    first_name, *rest = unidecode(name).lower().split(' ')
    return f"{''.join(rest)}-{first_name}"


def is_metadata_file(filename: str) -> bool:
    """
    Checks if the given filename is a text file containing metadata about the submission.
    """
    METADATA_FILE_REGEX = r'.*_q\d{7}_(poging|attempt)_\d{4}-\d{2}-\d{2}-\d{2}-\d{2}-\d{2}\.txt'
    return bool(re.fullmatch(METADATA_FILE_REGEX, filename))


def extract_name_and_qid_from_metadata(metadata: str) -> tuple[str, str]:
    match = re.search(r'(?:Name|Naam): (.*) \((q\d+)\)', metadata)

    if not match:
        raise MetadataError('Failed to extract name')

    name = match.group(1)
    qid = match.group(2)

    return (name, qid)


def find_submitted_files(metadata: str) -> dict[str, str]:
    actual_name: str = 'dummy'
    result = {}

    for line in metadata.splitlines():
        if match := re.fullmatch(r'\s+(?:Oorspronkelijke bestandsnaam|Original filename): (.*)', line):
            actual_name = match.group(1)
        if match := re.fullmatch(r'\s+(?:Bestandsnaam|Filename): (.*)', line):
            name_in_submission = match.group(1)
            result[name_in_submission] = actual_name

    return result


def parse_metadata(metadata: str) -> Metadata:
    name, qid = extract_name_and_qid_from_metadata(metadata)
    submitted_files = find_submitted_files(metadata)
    return Metadata(name=name, qid=qid, submitted_files=submitted_files)


def extract_metadata_from_archive(archive: ZipFile) -> Iterable[Metadata]:
    contents = archive.namelist()
    meta_filenames = (filename for filename in contents if is_metadata_file(filename))
    for meta_filename in meta_filenames:
        data = archive.read(meta_filename).decode('utf-8')
        yield parse_metadata(data)
