# Copyright (c) 2019 NVIDIA Corporation
import collections
import os
from typing import List, Optional, Union

import pandas as pd

import nemo
from nemo.collections.asr.parts import manifest, parsers


class _Collection(collections.UserList):
    """List of parsed and preprocessed data."""

    OUTPUT_TYPE = None  # Single element output type.


class Text(_Collection):
    """Simple list of preprocessed text entries, result in list of tokens."""

    OUTPUT_TYPE = collections.namedtuple('TextEntity', 'tokens')

    def __init__(self, texts: List[str], parser: parsers.CharParser):
        """Instantiates text manifest and do the preprocessing step.

        Args:
            texts: List of raw texts strings.
            parser: Instance of `CharParser` to convert string to tokens.
        """

        data, output_type = [], self.OUTPUT_TYPE
        for text in texts:
            tokens = parser(text)

            if tokens is None:
                nemo.logging.warning("Fail to parse '%s' text line.", text)
                continue

            data.append(output_type(tokens))

        super().__init__(data)


class FromFileText(Text):
    """Another form of texts manifest with reading from file."""

    def __init__(self, file: str, parser: parsers.CharParser):
        """Instantiates text manifest and do the preprocessing step.

        Args:
            file: File path to read from.
            parser: Instance of `CharParser` to convert string to tokens.
        """

        texts = self.__parse_texts(file)

        super().__init__(texts, parser)

    @staticmethod
    def __parse_texts(file: str) -> List[str]:
        if not os.path.exists(file):
            raise ValueError('Provided texts file does not exists!')

        _, ext = os.path.splitext(file)
        if ext == '.csv':
            texts = pd.read_csv(file)['transcript'].tolist()
        elif ext == '.json':  # Not really a correct json.
            texts = list(item['text'] for item in manifest.item_iter(file))
        else:
            with open(file, 'r') as f:
                texts = f.readlines()

        return texts


class AudioText(_Collection):
    """List of audio-transcript text correspondence with preprocessing."""

    OUTPUT_TYPE = collections.namedtuple(typename='AudioTextEntity', field_names='audio_file duration text_tokens',)

    def __init__(
        self,
        audio_files: List[str],
        durations: List[float],
        texts: List[str],
        parser: parsers.CharParser,
        min_duration: Optional[float] = None,
        max_duration: Optional[float] = None,
        max_number: Optional[int] = None,
        do_sort_by_duration: bool = False,
    ):
        """Instantiates audio-text manifest with filters and preprocessing.

        Args:
            audio_files: List of audio files.
            durations: List of float durations.
            texts: List of raw text transcripts.
            parser: Instance of `CharParser` to convert string to tokens.
            min_duration: Minimum duration to keep entry with (default: None).
            max_duration: Maximum duration to keep entry with (default: None).
            max_number: Maximum number of samples to collect.
            do_sort_by_duration: True if sort samples list by duration.
        """

        output_type = self.OUTPUT_TYPE
        data, duration_filtered = [], 0.0
        for audio_file, duration, text in zip(audio_files, durations, texts):
            # Duration filters.
            if min_duration is not None and duration < min_duration:
                duration_filtered += duration
                continue

            if max_duration is not None and duration > max_duration:
                duration_filtered += duration
                continue

            text_tokens = parser(text)
            if text_tokens is None:
                duration_filtered += duration
                continue

            data.append(output_type(audio_file, duration, text_tokens))

            # Max number of entities filter.
            if len(data) == max_number:
                break

        if do_sort_by_duration:
            data.sort(key=lambda entity: entity.duration)

        nemo.logging.info(
            "Filtered duration for loading collection is %f.", duration_filtered,
        )

        super().__init__(data)


class ASRAudioText(AudioText):
    """`AudioText` collector from asr structured json files."""

    def __init__(self, manifests_files: Union[str, List[str]], *args, **kwargs):
        """Parse lists of audio files, durations and transcripts texts.

        Args:
            manifests_files: Either single string file or list of such -
                manifests to yield items from.
            *args: Args to pass to `AudioText` constructor.
            **kwargs: Kwargs to pass to `AudioText` constructor.
        """

        audio_files, durations, texts = [], [], []
        for item in manifest.item_iter(manifests_files):
            audio_files.append(item['audio_file'])
            durations.append(item['duration'])
            texts.append(item['text'])

        super().__init__(audio_files, durations, texts, *args, **kwargs)
