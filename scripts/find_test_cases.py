#!/usr/bin/env python3
"""Find test cases with different sizes and complexity for LLM performance testing."""

import json
import os
import glob

def get_case_stats(file_path):
    """Get statistics for a case file."""
    try:
        with open(file_path, 'r', encoding='utf-8') as f:
            data = json.load(f)
        
        docket_count = len(data.get('docket_entries', []))
        file_size = os.path.getsize(file_path)
        
        # Get text content length
        text_parts = []
        for field in ["style_of_cause", "title", "nature_of_proceeding"]:
            value = data.get(field, "")
            if value:
                text_parts.append(value)
        
        for de in data.get("docket_entries") or []:
            summary = de.get("summary", "")
            if summary:
                text_parts.append(summary)
        
        text_length = len(" ".join(text_parts))
        
        return {
            'file': os.path.basename(file_path),
            'size_kb': round(file_size / 1024, 2),
            'docket_entries': docket_count,
            'text_length': text_length,
            'file_path': file_path,
            'case_number': data.get('case_number', ''),
            'title': data.get('title', ''),
            'nature_of_proceeding': data.get('nature_of_proceeding', '')
        }
    except Exception as e:
        print(f"Error processing {file_path}: {e}")
        return None

def main():
    # Get all JSON files
    json_files = glob.glob('/home/watson/work/FCT-AutoQuery/output/json/2021/*.json')
    stats = []

    for file_path in json_files:
        stat = get_case_stats(file_path)
        if stat:
            stats.append(stat)

    # Sort by different metrics
    stats_by_size = sorted(stats, key=lambda x: x['size_kb'])
    stats_by_dockets = sorted(stats, key=lambda x: x['docket_entries'])
    stats_by_text = sorted(stats, key=lambda x: x['text_length'])

    print('=== SMALLEST FILES (by size) ===')
    for stat in stats_by_size[:5]:
        print(f"{stat['file']}: {stat['size_kb']}KB, {stat['docket_entries']} docket entries, {stat['text_length']} chars")
        print(f"  Case: {stat['case_number']} - {stat['title'][:50]}...")
        print(f"  Nature: {stat['nature_of_proceeding'][:50]}...")
        print()

    print('=== LARGEST FILES (by size) ===')
    for stat in stats_by_size[-5:]:
        print(f"{stat['file']}: {stat['size_kb']}KB, {stat['docket_entries']} docket entries, {stat['text_length']} chars")
        print(f"  Case: {stat['case_number']} - {stat['title'][:50]}...")
        print(f"  Nature: {stat['nature_of_proceeding'][:50]}...")
        print()

    print('=== MOST DOCKET ENTRIES ===')
    for stat in stats_by_dockets[-5:]:
        print(f"{stat['file']}: {stat['docket_entries']} entries, {stat['size_kb']}KB, {stat['text_length']} chars")
        print(f"  Case: {stat['case_number']} - {stat['title'][:50]}...")
        print()

    print('=== MEDIUM SIZE CASES (for balanced testing) ===')
    # Find cases in the middle range
    mid_size = stats_by_text[len(stats_by_text)//2 - 2:len(stats_by_text)//2 + 3]
    for stat in mid_size:
        print(f"{stat['file']}: {stat['text_length']} chars, {stat['docket_entries']} entries, {stat['size_kb']}KB")
        print(f"  Case: {stat['case_number']} - {stat['title'][:50]}...")
        print()

    # Search for potential mandamus-related content
    print('=== CASES WITH KEYWORDS RELATED TO MANDAMUS ===')
    keywords = ['delay', 'expedite', 'compel', 'unreasonable', 'speed', 'timely']
    
    for stat in stats:
        if any(keyword.lower() in stat['nature_of_proceeding'].lower() or 
               keyword.lower() in stat['title'].lower() 
               for keyword in keywords):
            print(f"{stat['file']}: {stat['size_kb']}KB, {stat['docket_entries']} entries")
            print(f"  Case: {stat['case_number']} - {stat['title']}")
            print(f"  Nature: {stat['nature_of_proceeding']}")
            print()

if __name__ == "__main__":
    main()