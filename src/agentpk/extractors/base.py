"""Abstract base class and data structures for language-specific signal extractors."""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from pathlib import Path


@dataclass
class NetworkCall:
    method: str          # GET, POST, PUT, DELETE, PATCH, UNKNOWN
    library: str         # requests, axios, net/http, etc.
    file: str
    line: int


@dataclass
class FileOperation:
    operation: str       # read, write
    file: str
    line: int


@dataclass
class SubprocessCall:
    command: str         # best-effort extracted command
    file: str
    line: int


@dataclass
class EnvVarAccess:
    var_name: str        # best-effort, may be UNKNOWN for dynamic access
    file: str
    line: int


@dataclass
class ToolRegistration:
    framework: str       # langchain, openai, crewai, autogen, langchain-js, spring-ai, etc.
    tool_name: str
    file: str
    line: int


@dataclass
class ImportRecord:
    module: str
    file: str
    line: int


@dataclass
class StaticAnalysisFindings:
    language: str = ""
    imports: list[ImportRecord] = field(default_factory=list)
    network_calls: list[NetworkCall] = field(default_factory=list)
    file_reads: list[FileOperation] = field(default_factory=list)
    file_writes: list[FileOperation] = field(default_factory=list)
    subprocess_calls: list[SubprocessCall] = field(default_factory=list)
    env_var_accesses: list[EnvVarAccess] = field(default_factory=list)
    tool_registrations: list[ToolRegistration] = field(default_factory=list)
    entry_functions: list[str] = field(default_factory=list)
    dynamic_import_detected: bool = False
    obfuscated_call_detected: bool = False
    extractor_warnings: list[str] = field(default_factory=list)


class ExtractorBase(ABC):
    """Base class for all language-specific signal extractors."""

    @property
    @abstractmethod
    def language(self) -> str:
        """The language identifier this extractor handles (e.g. 'python', 'nodejs')."""
        ...

    @property
    @abstractmethod
    def file_extensions(self) -> list[str]:
        """File extensions this extractor processes (e.g. ['.py'])."""
        ...

    @abstractmethod
    def extract(self, source_files: list[Path]) -> StaticAnalysisFindings:
        """
        Analyze source files and return a StaticAnalysisFindings record.
        Must not execute any source code.
        Must be deterministic: same input -> same output.
        """
        ...

    def supports_file(self, path: Path) -> bool:
        return path.suffix.lower() in self.file_extensions
