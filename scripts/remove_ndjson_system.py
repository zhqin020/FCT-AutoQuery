#!/usr/bin/env python3
"""Remove NDJSON system completely from the codebase."""

import argparse
import os
import shutil
import sys
from pathlib import Path
import subprocess
import datetime

# Add src to path
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from src.lib.logging_config import get_logger

logger = get_logger()


class NDJSONRemover:
    """Remove NDJSON system from the codebase."""
    
    def __init__(self):
        self.project_root = Path(__file__).parent.parent
        self.backup_dir = self.project_root / "logs" / "backup"
        
    def backup_ndjson_files(self):
        """Backup existing NDJSON files."""
        ndjson_files = list(self.project_root.glob("logs/run_*.ndjson"))
        
        if not ndjson_files:
            logger.info("No NDJSON files found to backup")
            return True
            
        self.backup_dir.mkdir(parents=True, exist_ok=True)
        timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
        backup_path = self.backup_dir / f"ndjson_backup_{timestamp}"
        backup_path.mkdir(exist_ok=True)
        
        try:
            for ndjson_file in ndjson_files:
                shutil.copy2(ndjson_file, backup_path / ndjson_file.name)
                logger.info(f"Backed up: {ndjson_file}")
            
            logger.info(f"NDJSON files backed up to: {backup_path}")
            return True
            
        except Exception as e:
            logger.error(f"Failed to backup NDJSON files: {e}")
            return False
    
    def remove_ndjson_files(self):
        """Remove NDJSON files."""
        ndjson_files = list(self.project_root.glob("logs/run_*.ndjson"))
        
        if not ndjson_files:
            logger.info("No NDJSON files found to remove")
            return True
            
        try:
            for ndjson_file in ndjson_files:
                ndjson_file.unlink()
                logger.info(f"Removed: {ndjson_file}")
            
            logger.info("All NDJSON files removed")
            return True
            
        except Exception as e:
            logger.error(f"Failed to remove NDJSON files: {e}")
            return False
    
    def remove_run_logger_py(self):
        """Remove the # run_logger.py file."""
        run_logger_path = self.project_root / "src" / "lib" / "# run_logger.py"
        
        if not run_logger_path.exists():
            logger.info("# run_logger.py not found")
            return True
            
        try:
            run_logger_path.unlink()
            logger.info(f"Removed: {run_logger_path}")
            return True
            
        except Exception as e:
            logger.error(f"Failed to remove # run_logger.py: {e}")
            return False
    
    def find_run_logger_imports(self):
        """Find files that import RunLogger."""
        files_with_imports = []

        for py_file in self.project_root.rglob("*.py"):
            if "node_modules" in str(py_file) or ".git" in str(py_file):
                continue

            try:
                content = py_file.read_text(encoding='utf-8')
            except Exception as e:
                logger.debug(f"Could not read {py_file}: {e}")
                continue

            if (
                'from src.lib.run_logger import' in content
                or 'import src.lib.run_logger' in content
                or 'RunLogger' in content
                or 'run_logger.' in content
            ):
                files_with_imports.append(py_file)

        return files_with_imports
    
    def remove_run_logger_imports(self, files):
        """Remove RunLogger imports from files."""
        for file_path in files:
            try:
                content = file_path.read_text(encoding='utf-8')
                original_content = content
                
                # Remove import lines
                lines = content.split('\n')
                new_lines = []

                for line in lines:
                    # Remove explicit imports of RunLogger
                    if ('from src.lib.run_logger import' in line
                        or 'import src.lib.run_logger' in line
                        or 'from .run_logger import' in line
                    ):
                        logger.info(f"Removing import from {file_path}: {line.strip()}")
                        continue

                    # Remove function args or parameters named run_logger
                    if 'run_logger' in line and ('RunLogger' in line or 'enable_run_logger' in line):
                        # Comment out parameters referencing run_logger
                        logger.info(f"Removing run_logger parameter usage in {file_path}: {line.strip()}")
                        new_lines.append('# ' + line)
                        continue

                    new_lines.append(line)
                
                # Remove or comment out RunLogger usage patterns
                content = '\n'.join(new_lines)
                content = content.replace('self.run_logger = RunLogger()', '# self.run_logger = RunLogger()  # Removed')
                content = content.replace('run_logger.finish()', '# run_logger.finish()  # Removed')
                content = content.replace('run_logger.start()', '# run_logger.start()  # Removed')
                content = content.replace('run_logger.', '# run_logger.  # Removed')  # Comment out usage
                
                if content != original_content:
                    file_path.write_text(content, encoding='utf-8')
                    logger.info(f"Updated: {file_path}")
                
            except Exception as e:
                logger.error(f"Failed to update {file_path}: {e}")
                return False
        
        return True
    
    def dry_run(self):
        """Show what would be removed without actually removing anything."""
        print("🔍 DRY RUN - Showing what would be removed:")
        print()
        
        # Check NDJSON files
        ndjson_files = list(self.project_root.glob("logs/run_*.ndjson"))
        print(f"NDJSON files to remove ({len(ndjson_files)}):")
        for f in ndjson_files:
            print(f"  - {f}")
        print()
        
        # Check # run_logger.py
        run_logger_path = self.project_root / "src" / "lib" / "# run_logger.py"
        if run_logger_path.exists():
            print(f"Files to remove:")
            print(f"  - {run_logger_path}")
        print()
        
        # Check imports
        files_with_imports = self.find_run_logger_imports()
        print(f"Files with RunLogger imports to update ({len(files_with_imports)}):")
        for f in files_with_imports:
            print(f"  - {f}")
        print()
        
        return True
    
    def execute_removal(self, backup=True):
        """Execute the NDJSON system removal."""
        logger.info("Starting NDJSON system removal...")
        
        # Step 1: Backup if requested
        if backup:
            if not self.backup_ndjson_files():
                return False
        
        # Step 2: Remove NDJSON files
        if not self.remove_ndjson_files():
            return False
        
        # Step 3: Remove # run_logger.py
        if not self.remove_run_logger_py():
            return False
        
        # Step 4: Remove imports
        files_with_imports = self.find_run_logger_imports()
        if files_with_imports:
            if not self.remove_run_logger_imports(files_with_imports):
                return False
        
        logger.info("NDJSON system removal completed successfully!")
        return True


def main():
    parser = argparse.ArgumentParser(description="Remove NDJSON system from the codebase")
    parser.add_argument("--dry-run", action="store_true", help="Show what would be removed without removing")
    parser.add_argument("--confirm", action="store_true", help="Confirm removal")
    parser.add_argument("--no-backup", action="store_true", help="Skip backup of NDJSON files")
    
    args = parser.parse_args()
    
    remover = NDJSONRemover()
    
    if args.dry_run:
        return remover.dry_run()
    
    if not args.confirm:
        print("❌ Please use --confirm to proceed with removal")
        print("💡 Use --dry-run first to see what will be removed")
        return False
    
    backup = not args.no_backup
    success = remover.execute_removal(backup=backup)
    
    if success:
        print("✅ NDJSON system removed successfully!")
        return True
    else:
        print("❌ Failed to remove NDJSON system!")
        return False


if __name__ == "__main__":
    success = main()
    sys.exit(0 if success else 1)