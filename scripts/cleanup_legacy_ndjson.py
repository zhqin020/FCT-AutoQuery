#!/usr/bin/env python3
"""
清理遗留的NDJSON文件和RunLogger依赖

此脚本用于在完成数据库迁移后，清理所有NDJSON相关的文件和代码引用。
"""

import os
import shutil
import argparse
import sys
from pathlib import Path
from typing import List, Optional
import re

def find_ndjson_files(logs_dir: str = "logs") -> List[Path]:
    """查找所有NDJSON文件"""
    logs_path = Path(logs_dir)
    if not logs_path.exists():
        return []
    
    ndjson_files = list(logs_path.glob("run_*.ndjson"))
    return ndjson_files

def backup_ndjson_files(
    ndjson_files: List[Path], 
    backup_dir: str = "logs/backup"
) -> bool:
    """备份NDJSON文件"""
    backup_path = Path(backup_dir)
    backup_path.mkdir(parents=True, exist_ok=True)
    
    success = True
    for ndjson_file in ndjson_files:
        try:
            backup_file = backup_path / ndjson_file.name
            shutil.copy2(ndjson_file, backup_file)
            print(f"备份: {ndjson_file} -> {backup_file}")
        except Exception as e:
            print(f"备份失败 {ndjson_file}: {e}")
            success = False
    
    return success

def remove_ndjson_files(ndjson_files: List[Path]) -> bool:
    """删除NDJSON文件"""
    success = True
    for ndjson_file in ndjson_files:
        try:
            ndjson_file.unlink()
            print(f"删除: {ndjson_file}")
        except Exception as e:
            print(f"删除失败 {ndjson_file}: {e}")
            success = False
    
    return success

def find_runlogger_references(src_dir: str = "src") -> List[Path]:
    """查找包含RunLogger引用的Python文件"""
    src_path = Path(src_dir)
    python_files = list(src_path.rglob("*.py"))
    
    files_with_references = []
    for py_file in python_files:
        try:
            with open(py_file, 'r', encoding='utf-8') as f:
                content = f.read()
                if 'RunLogger' in content or 'run_logger' in content:
                    files_with_references.append(py_file)
        except Exception as e:
            print(f"读取文件失败 {py_file}: {e}")
    
    return files_with_references

def remove_runlogger_imports(file_path: Path) -> bool:
    """移除文件中的RunLogger导入"""
    try:
        with open(file_path, 'r', encoding='utf-8') as f:
            lines = f.readlines()
        
        new_lines = []
        removed_imports = []
        
        for line in lines:
            # 移除RunLogger相关的导入
            if (
                'from src.lib.run_logger import' in line
                or 'import src.lib.run_logger' in line
                or 'from .run_logger import RunLogger' in line
            ):
                removed_imports.append(line.strip())
                continue
            
            # 移除RunLogger参数
            if 'run_logger' in line and ('RunLogger' in line or 'enable_run_logger' in line):
                # 简单的注释处理
                new_lines.append(f"# REMOVED: {line}")
                continue
            
            new_lines.append(line)
        
        if removed_imports:
            with open(file_path, 'w', encoding='utf-8') as f:
                f.writelines(new_lines)
            print(f"移除导入 {file_path}: {', '.join(removed_imports)}")
            return True
        
    except Exception as e:
        print(f"处理文件失败 {file_path}: {e}")
    
    return False

def remove_runlogger_file() -> bool:
    """删除# run_logger.py文件"""
    runlogger_path = Path("src/lib/run_logger.py")
    if runlogger_path.exists():
        try:
            runlogger_path.unlink()
            print(f"删除文件: {runlogger_path}")
            return True
        except Exception as e:
            print(f"删除失败 {runlogger_path}: {e}")
    return False

def update_config_files() -> bool:
    """更新配置文件，移除run_logger相关配置"""
    config_files = [
        "config.example.toml",
        "pyproject.toml"
    ]
    
    success = True
    for config_file in config_files:
        config_path = Path(config_file)
        if not config_path.exists():
            continue
        
        try:
            with open(config_path, 'r', encoding='utf-8') as f:
                content = f.read()
            
            # 移除run_logger相关配置
            original_content = content
            
            # 移除enable_run_logger配置
            content = re.sub(r'enable_run_logger\s*=\s*.*?\n', '', content)
            content = re.sub(r'#.*enable_run_logger.*?\n', '', content)
            
            if content != original_content:
                with open(config_path, 'w', encoding='utf-8') as f:
                    f.write(content)
                print(f"更新配置: {config_file}")
        
        except Exception as e:
            print(f"更新配置失败 {config_file}: {e}")
            success = False
    
    return success

def main():
    parser = argparse.ArgumentParser(description="清理遗留的NDJSON文件和RunLogger依赖")
    parser.add_argument("--backup", default="logs/backup", help="备份目录")
    parser.add_argument("--logs-dir", default="logs", help="日志目录")
    parser.add_argument("--src-dir", default="src", help="源代码目录")
    parser.add_argument("--dry-run", action="store_true", help="仅显示将要执行的操作")
    parser.add_argument("--confirm", action="store_true", help="确认执行操作")
    
    args = parser.parse_args()
    
    # 查找NDJSON文件
    ndjson_files = find_ndjson_files(args.logs_dir)
    print(f"找到 {len(ndjson_files)} 个NDJSON文件")
    for f in ndjson_files:
        print(f"  - {f}")
    
    # 查找RunLogger引用
    files_with_references = find_runlogger_references(args.src_dir)
    print(f"找到 {len(files_with_references)} 个包含RunLogger引用的文件")
    for f in files_with_references:
        print(f"  - {f}")
    
    if not args.confirm:
        print("\n使用 --confirm 参数执行实际清理操作")
        print("使用 --dry-run 参数查看将要执行的操作")
        return
    
    if args.dry_run:
        print("\n=== 干运行模式 ===")
        print("将要执行的操作:")
        print(f"1. 备份 {len(ndjson_files)} 个NDJSON文件到 {args.backup}")
        print(f"2. 删除 {len(ndjson_files)} 个NDJSON文件")
        print(f"3. 移除 {len(files_with_references)} 个文件中的RunLogger引用")
        print("4. 删除 src/lib/run_logger.py")
        print("5. 更新配置文件")
        return
    
    print("\n=== 开始清理 ===")
    
    # 1. 备份NDJSON文件
    if ndjson_files:
        print("\n1. 备份NDJSON文件...")
        if not backup_ndjson_files(ndjson_files, args.backup):
            print("备份失败，停止操作")
            sys.exit(1)
    
    # 2. 删除NDJSON文件
    if ndjson_files:
        print("\n2. 删除NDJSON文件...")
        if not remove_ndjson_files(ndjson_files):
            print("删除失败，但继续操作")
    
    # 3. 移除RunLogger引用
    if files_with_references:
        print("\n3. 移除RunLogger引用...")
        for file_path in files_with_references:
            remove_runlogger_imports(file_path)
    
    # 4. 删除# run_logger.py文件
    print("\n4. 删除# run_logger.py文件...")
    remove_runlogger_file()
    
    # 5. 更新配置文件
    print("\n5. 更新配置文件...")
    update_config_files()
    
    print("\n=== 清理完成 ===")
    print("请检查代码是否正常工作，并提交更改")

if __name__ == "__main__":
    main()