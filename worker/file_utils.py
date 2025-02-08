import hashlib
import logging
import os
import shutil
import stat
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional, Set, Tuple

import win32api
import win32con
import win32security
from win32com.shell import shell, shellcon

logger = logging.getLogger(__name__)


class FileUtils:
    """Classe utilitária para operações com arquivos"""

    @staticmethod
    def get_file_info(file_path: str) -> Dict:
        """
        Obtém informações detalhadas de um arquivo.

        Args:
            file_path: Caminho do arquivo

        Returns:
            Dicionário com informações do arquivo
        """
        try:
            stat_info = os.stat(file_path)

            # Obtém informações de segurança do Windows
            sec_desc = win32security.GetFileSecurity(
                file_path,
                win32security.OWNER_SECURITY_INFORMATION
                | win32security.GROUP_SECURITY_INFORMATION,
            )

            owner_sid = sec_desc.GetSecurityDescriptorOwner()
            group_sid = sec_desc.GetSecurityDescriptorGroup()

            owner_name = win32security.LookupAccountSid(None, owner_sid)[0]
            group_name = win32security.LookupAccountSid(None, group_sid)[0]

            return {
                "size": stat_info.st_size,
                "created": datetime.fromtimestamp(stat_info.st_ctime),
                "modified": datetime.fromtimestamp(stat_info.st_mtime),
                "accessed": datetime.fromtimestamp(stat_info.st_atime),
                "owner": owner_name,
                "group": group_name,
                "permissions": stat_info.st_mode,
                "attributes": win32api.GetFileAttributes(file_path),
            }
        except Exception as e:
            logger.error(f"Error getting file info for {file_path}: {str(e)}")
            raise

    @staticmethod
    def calculate_md5(file_path: str, block_size: int = 8192) -> str:
        """
        Calcula o hash MD5 de um arquivo.

        Args:
            file_path: Caminho do arquivo
            block_size: Tamanho do bloco para leitura

        Returns:
            Hash MD5 em hexadecimal
        """
        md5 = hashlib.md5()
        try:
            with open(file_path, "rb") as f:
                while True:
                    data = f.read(block_size)
                    if not data:
                        break
                    md5.update(data)
            return md5.hexdigest()
        except Exception as e:
            logger.error(f"Error calculating MD5 for {file_path}: {str(e)}")
            raise

    @staticmethod
    def copy_with_metadata(
        source: str, destination: str, preserve_acl: bool = True
    ) -> None:
        """
        Copia um arquivo preservando todos os metadados.

        Args:
            source: Caminho do arquivo fonte
            destination: Caminho de destino
            preserve_acl: Se deve preservar as ACLs
        """
        try:
            # Cria diretórios de destino se necessário
            os.makedirs(os.path.dirname(destination), exist_ok=True)

            # Copia o arquivo com metadados
            shutil.copy2(source, destination)

            if preserve_acl:
                # Copia ACLs do Windows
                sec_desc = win32security.GetFileSecurity(
                    source, win32security.DACL_SECURITY_INFORMATION
                )
                win32security.SetFileSecurity(
                    destination,
                    win32security.DACL_SECURITY_INFORMATION,
                    sec_desc,
                )

            # Copia atributos do Windows
            attrs = win32api.GetFileAttributes(source)
            win32api.SetFileAttributes(destination, attrs)

        except Exception as e:
            logger.error(f"Error copying {source} to {destination}: {str(e)}")
            raise

    @staticmethod
    def safe_delete(path: str) -> None:
        """
        Remove um arquivo ou diretório de forma segura.

        Args:
            path: Caminho a ser removido
        """
        try:
            if os.path.isfile(path):
                # Remove atributos somente leitura
                attrs = win32api.GetFileAttributes(path)
                if attrs & win32con.FILE_ATTRIBUTE_READONLY:
                    win32api.SetFileAttributes(
                        path, attrs & ~win32con.FILE_ATTRIBUTE_READONLY
                    )
                os.remove(path)
            elif os.path.isdir(path):
                shutil.rmtree(path)
        except Exception as e:
            logger.error(f"Error deleting {path}: {str(e)}")
            raise

    @staticmethod
    def get_free_space(path: str) -> int:
        """
        Obtém o espaço livre em um caminho.

        Args:
            path: Caminho para verificar

        Returns:
            Espaço livre em bytes
        """
        try:
            return shutil.disk_usage(path).free
        except Exception as e:
            logger.error(f"Error getting free space for {path}: {str(e)}")
            raise

    @staticmethod
    def map_directory(
        path: str, exclusions: Optional[Set[str]] = None
    ) -> List[Dict]:
        """
        Mapeia um diretório retornando informações de todos os arquivos.

        Args:
            path: Diretório a ser mapeado
            exclusions: Conjunto de padrões a serem excluídos

        Returns:
            Lista de dicionários com informações dos arquivos
        """
        files_info = []
        try:
            for root, _, files in os.walk(path):
                for file in files:
                    file_path = os.path.join(root, file)

                    # Verifica exclusões
                    if exclusions:
                        if any(excl in file_path for excl in exclusions):
                            continue

                    try:
                        info = FileUtils.get_file_info(file_path)
                        info["path"] = file_path
                        info["relative_path"] = os.path.relpath(
                            file_path, path
                        )
                        files_info.append(info)
                    except Exception as e:
                        logger.warning(
                            f"Error getting info for {file_path}: {str(e)}"
                        )

            return files_info
        except Exception as e:
            logger.error(f"Error mapping directory {path}: {str(e)}")
            raise

    @staticmethod
    def cleanup_old_logs(
        log_dir: str, days: int, pattern: str = "*.csv"
    ) -> None:
        """
        Remove arquivos de log antigos.

        Args:
            log_dir: Diretório de logs
            days: Dias para manter
            pattern: Padrão dos arquivos de log
        """
        try:
            now = datetime.now()
            for file in Path(log_dir).glob(pattern):
                if (
                    now - datetime.fromtimestamp(file.stat().st_mtime)
                ).days > days:
                    try:
                        file.unlink()
                    except Exception as e:
                        logger.error(f"Error deleting log {file}: {str(e)}")
        except Exception as e:
            logger.error(f"Error cleaning logs in {log_dir}: {str(e)}")
            raise

    @staticmethod
    def is_path_accessible(path: str) -> bool:
        """
        Verifica se um caminho é acessível para leitura/escrita.

        Args:
            path: Caminho a ser verificado

        Returns:
            True se o caminho é acessível
        """
        try:
            # Verifica se o caminho existe
            if not os.path.exists(path):
                return False

            # Tenta criar um arquivo temporário
            test_file = os.path.join(path, "test_access_123.tmp")
            try:
                with open(test_file, "w") as f:
                    f.write("test")
                os.remove(test_file)
                return True
            except:
                return False

        except Exception:
            return False

    @staticmethod
    def format_size(size_bytes: int) -> str:
        """
        Formata um tamanho em bytes para formato legível.

        Args:
            size_bytes: Tamanho em bytes

        Returns:
            String formatada (ex: "1.5 GB")
        """
        for unit in ["B", "KB", "MB", "GB", "TB"]:
            if size_bytes < 1024:
                return f"{size_bytes:.2f} {unit}"
            size_bytes /= 1024
        return f"{size_bytes:.2f} PB"


# Exemplo de uso:
"""
# Obtém informações de um arquivo
file_info = FileUtils.get_file_info("C:\\path\\to\\file.txt")

# Calcula MD5
md5 = FileUtils.calculate_md5("C:\\path\\to\\file.txt")

# Copia preservando metadados
FileUtils.copy_with_metadata(
    "C:\\source\\file.txt",
    "D:\\backup\\file.txt"
)

# Mapeia diretório
files = FileUtils.map_directory(
    "C:\\Documents",
    exclusions={".tmp", ".temp"}
)

# Limpa logs antigos
FileUtils.cleanup_old_logs("logs", days=180)

# Verifica espaço
free_space = FileUtils.get_free_space("D:\\")
print(f"Free space: {FileUtils.format_size(free_space)}")
"""
