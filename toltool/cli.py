from rich.console import Console
from rich.table import Table
from pathlib import Path
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


class Submission(pydantic.BaseModel):
    name: str
    qid: str
    files: dict[str, str]


def process_command_line_arguments():
    cli()


@click.group()
def cli():
    ...


@cli.command()
@click.argument('archive', type=str)
def view(archive):
    console = Console()

    with ZipFile(archive) as file:
        submissions = find_submissions(file)

        table = Table(show_header=True, header_style='blue')
        table.add_column('Name')
        table.add_column('Qid')
        table.add_column('Submitted files')

        for submission in submissions:
            table.add_row(submission.name, submission.qid, " ".join(submission.files.values()))

        console.print(table)


@cli.command()
@click.argument('archive', type=str)
def unpack(archive):
    with ZipFile(archive) as file:
        submissions = find_submissions(file)

        for submission in submissions:
            extract_all_files_from_submission(file, submission)


def extract_all_files_from_submission(archive: ZipFile, submission: Submission) -> None:
    """
    Extracts all files from a single submission.
    """
    directory = slug_from_name(submission.name)

    if not os.path.exists(directory):
            os.mkdir(directory)

    if len(submission.files) == 0:
        print(f'WARNING: {submission.name} ({submission.qid}) has submitted 0 files')

    for (filename_in_archive, target_filename) in submission.files.items():
        extract_submission_file(
            archive=archive,
            filename_in_archive=filename_in_archive,
            target_filename=target_filename,
            directory=directory
        )


def extract_submission_file(archive: ZipFile, filename_in_archive: str, target_filename: str, directory: str) -> None:
    """
    Extracts a submitted file from the archive.
    If this file is a zip, this zip will be unpacked.
    """
    if target_filename.endswith('.zip'):
        extract_submitted_zipfile(archive, filename_in_archive, directory)
    else:
        extract_submitted_nonzipfile(archive, filename_in_archive, target_filename, directory)


def extract_submitted_zipfile(archive: ZipFile, filename_in_archive: str, directory: str) -> None:
    """
    A student submitted a zipfile.
    This function extracts this zipfile from the archive and unzips it into the given directory.
    """
    buffer = BytesIO(archive.read(filename_in_archive))
    with ZipFile(buffer, 'r') as submitted_file:
        submitted_file.extractall(directory)


def extract_submitted_nonzipfile(archive: ZipFile, filename_in_archive: str, target_filename: str, directory: str):
    """
    Extracts a file from the archive and stores it in the given directory.
    No special steps are taken.
    """
    original_path = Path.cwd() / directory / filename_in_archive
    target_path = Path.cwd() / directory / target_filename
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


def parse_metadata(metadata: str) -> Submission:
    """
    Given a submission's metadata, this function extracts the submitter's name,
    their q-id and the files they submitted.
    """
    name, qid = extract_name_and_qid_from_metadata(metadata)
    submitted_files = find_submitted_files(metadata)
    return Submission(name=name, qid=qid, files=submitted_files)


def find_submissions(archive: ZipFile) -> Iterable[Submission]:
    """
    Generates all submissions in the given archive.
    """
    contents = archive.namelist()
    meta_filenames = (filename for filename in contents if is_metadata_file(filename))
    for meta_filename in meta_filenames:
        raw_data = archive.read(meta_filename).decode('utf-8')
        try:
            data = parse_metadata(raw_data)
            yield data
        except MetadataError:
            print(f"Error: could not parse metadata from ${meta_filename}", file=sys.stderr)
