# -*- coding: utf-8 -*-

import sys
import json
import os
import subprocess
import platform
import webbrowser
import re
from pathlib import Path
from datetime import datetime
import urllib.parse
import time

class ObsidianPlugin:
    def __init__(self):
        self.obsidian_path = self.find_obsidian_path()
        self.vaults = self.find_vaults()
        self.vaults_cache = {}
        self.cache_timestamp = 0
        self.cache_duration = 300  # 5 minutes cache
        self.known_commands = [
            "open", "search", "new", "vault", "daily", "recent", "vaults", "help"
        ]

    def find_obsidian_path(self):
        """Find Obsidian executable path"""
        if platform.system() == 'Windows':
            paths = [
                os.path.join(os.environ.get('LOCALAPPDATA', ''), 'Obsidian', 'Obsidian.exe'),
                os.path.join(os.environ.get('PROGRAMFILES', ''), 'Obsidian', 'Obsidian.exe'),
                os.path.join(os.environ.get('PROGRAMFILES(X86)', ''), 'Obsidian', 'Obsidian.exe'),
                r'C:\Program Files\Obsidian\Obsidian.exe',
                r'C:\Program Files (x86)\Obsidian\Obsidian.exe'
            ]
            for path in paths:
                if os.path.exists(path):
                    return path
        elif platform.system() == 'Darwin':
            return '/Applications/Obsidian.app/Contents/MacOS/Obsidian'
        else:
            # Linux
            return '/usr/bin/obsidian'

        return None

    def find_vaults(self):
        """Find all Obsidian vaults with comprehensive search and vault IDs"""
        vaults = []

        # First, try to get registered vaults from Obsidian's global config
        obsidian_config_path = self.get_obsidian_config_path()
        registered_vaults = {}

        if obsidian_config_path and os.path.exists(obsidian_config_path):
            try:
                with open(obsidian_config_path, 'r', encoding='utf-8') as f:
                    config = json.load(f)
                    registered_vaults = config.get('vaults', {})
            except:
                pass

        # Get all drive letters on Windows
        drives = []
        if platform.system() == 'Windows':
            for letter in 'ABCDEFGHIJKLMNOPQRSTUVWXYZ':
                drive = f'{letter}:\\'
                if os.path.exists(drive):
                    drives.append(drive)

        # Common search paths
        search_paths = []

        # User profile paths
        user_profile = os.environ.get('USERPROFILE', '')
        home = os.environ.get('HOME', user_profile)

        if user_profile or home:
            base_profile = user_profile or home
            search_paths.extend([
                os.path.join(base_profile, 'Documents'),
                os.path.join(base_profile, 'OneDrive', 'Documents'),
                os.path.join(base_profile, 'Desktop'),
                os.path.join(base_profile, 'Notes'),
                os.path.join(base_profile, 'Obsidian'),
                os.path.join(base_profile, 'Dropbox'),
                os.path.join(base_profile, 'Google Drive'),
                os.path.join(base_profile, 'iCloudDrive'),
                base_profile
            ])

        # Add all drives for comprehensive search
        if platform.system() == 'Windows':
            for drive in drives:
                search_paths.extend([
                    drive,
                    os.path.join(drive, 'Users'),
                    os.path.join(drive, 'Documents'),
                    os.path.join(drive, 'Notes'),
                    os.path.join(drive, 'Obsidian')
                ])

        # Add registered vault paths
        for vault_id, vault_data in registered_vaults.items():
            if isinstance(vault_data, dict) and 'path' in vault_data:
                vault_path = vault_data['path']
                if os.path.exists(vault_path):
                    search_paths.append(vault_path)

        # Remove duplicates and non-existent paths
        search_paths = list(set(search_paths))
        search_paths = [path for path in search_paths if os.path.exists(path)]

        # Comprehensive search for .obsidian folders
        for search_path in search_paths:
            try:
                # Walk through directory tree to find .obsidian folders
                for root, dirs, files in os.walk(search_path):
                    # Skip hidden directories and common non-vault folders
                    dirs[:] = [d for d in dirs if not d.startswith('.') and d not in [
                        'node_modules', 'venv', '.git', '__pycache__', 'AppData', 'Program Files',
                        'Program Files (x86)', 'Windows', 'System32', 'temp', 'tmp', '$Recycle.Bin'
                    ]]

                    # Check if current directory is a vault (has .obsidian folder)
                    obsidian_config = os.path.join(root, '.obsidian')
                    if os.path.exists(obsidian_config) and os.path.isdir(obsidian_config):
                        vault_path = root
                        vault_name = os.path.basename(root)

                        # Get vault info
                        info = self.get_vault_info(vault_path)

                        # Find vault ID from registered vaults
                        vault_id = None
                        for vid, vdata in registered_vaults.items():
                            if isinstance(vdata, dict) and vdata.get('path') == vault_path:
                                vault_id = vid
                                break

                        vault_info = {
                            'name': vault_name,
                            'path': vault_path,
                            'config_path': obsidian_config,
                            'note_count': info['note_count'],
                            'recent_notes': info['recent_notes'],
                            'vault_id': vault_id,
                            'is_registered': vault_id is not None
                        }

                        # Avoid duplicates
                        if not any(v['path'] == vault_path for v in vaults):
                            vaults.append(vault_info)

                        # Remove .obsidian from dirs to avoid re-processing
                        dirs.remove('.obsidian')

            except PermissionError:
                continue
            except Exception as e:
                continue

        # Cache the results
        self.vaults_cache = {vault['path']: vault for vault in vaults}
        self.cache_timestamp = time.time()

        return vaults

    def get_obsidian_config_path(self):
        """Get path to Obsidian's main configuration file"""
        if platform.system() == 'Windows':
            return os.path.join(os.environ.get('APPDATA', ''), 'obsidian', 'obsidian.json')
        elif platform.system() == 'Darwin':
            return os.path.join(os.environ.get('HOME', ''), 'Library', 'Application Support', 'obsidian', 'obsidian.json')
        else:
            return os.path.join(os.environ.get('HOME', ''), '.config', 'obsidian', 'obsidian.json')

    def is_obsidian_running(self):
        """Check if Obsidian is currently running"""
        try:
            if platform.system() == 'Windows':
                tasks = subprocess.check_output('tasklist', shell=True).decode()
                return 'Obsidian.exe' in tasks
            elif platform.system() == 'Darwin':
                result = subprocess.run(['pgrep', '-x', 'Obsidian'], capture_output=True)
                return result.returncode == 0
            else:
                result = subprocess.run(['pidof', 'obsidian'], capture_output=True)
                return result.returncode == 0
        except:
            return False

    def launch_obsidian(self, vault_path=None):
        """Launch Obsidian, optionally opening a specific vault"""
        try:
            if vault_path:
                # Get the vault information from our database
                vault_info = None
                for vault in self.vaults:
                    if vault['path'] == vault_path:
                        vault_info = vault
                        break

                if vault_info:
                    # If vault is registered with Obsidian, use the vault ID
                    if vault_info.get('is_registered') and vault_info.get('vault_id'):
                        vault_uri = f'obsidian://open?vault={vault_info["vault_id"]}'
                        webbrowser.open(vault_uri)
                        return True
                    else:
                        # For unregistered vaults, try opening by path directly
                        # First ensure Obsidian is running
                        if not self.is_obsidian_running():
                            webbrowser.open('obsidian://open')
                            # Give Obsidian time to start
                            import time
                            time.sleep(2)

                        # Try to open the vault by path
                        if platform.system() == 'Windows':
                            try:
                                subprocess.Popen([self.obsidian_path, f'--path "{vault_path}"'])
                                return True
                            except:
                                pass

                        # Fallback: try URL with vault name
                        vault_name = vault_info['name']
                        vault_uri = f'obsidian://open?vault={urllib.parse.quote(vault_name)}'
                        webbrowser.open(vault_uri)
                        return True
                else:
                    return False

            # If no specific vault, just open Obsidian
            webbrowser.open('obsidian://open')
            return True

        except Exception as e:
            return False

    def get_vault_info(self, vault_path):
        """Get detailed information about a vault"""
        try:
            config_path = os.path.join(vault_path, '.obsidian', 'config')
            if os.path.exists(config_path):
                with open(config_path, 'r', encoding='utf-8') as f:
                    config = json.load(f)

            # Count notes
            note_count = 0
            recent_notes = []

            for root, dirs, files in os.walk(vault_path):
                # Skip .obsidian folder and other hidden dirs
                dirs[:] = [d for d in dirs if not d.startswith('.')]

                for file in files:
                    if file.endswith('.md'):
                        note_count += 1
                        file_path = os.path.join(root, file)
                        try:
                            mtime = os.path.getmtime(file_path)
                            recent_notes.append((file_path, mtime))
                        except:
                            continue

            # Sort by modification time and get recent ones
            recent_notes.sort(key=lambda x: x[1], reverse=True)
            recent_notes = recent_notes[:5]

            return {
                'note_count': note_count,
                'recent_notes': recent_notes,
                'config': config if 'config' in locals() else {}
            }
        except:
            return {'note_count': 0, 'recent_notes': [], 'config': {}}

    def search_notes(self, vault_path, query, limit=10):
        """Search for notes containing the query"""
        results = []
        query_lower = query.lower()

        try:
            for root, dirs, files in os.walk(vault_path):
                # Skip .obsidian folder
                dirs[:] = [d for d in dirs if d != '.obsidian' and not d.startswith('.')]

                for file in files:
                    if file.endswith('.md'):
                        file_path = os.path.join(root, file)
                        try:
                            with open(file_path, 'r', encoding='utf-8') as f:
                                content = f.read()
                                content_lower = content.lower()

                                # Check if query appears in title or content
                                title_match = file[:-3].lower().find(query_lower) >= 0
                                content_match = content_lower.find(query_lower) >= 0

                                if title_match or content_match:
                                    # Get relative path from vault
                                    rel_path = os.path.relpath(file_path, vault_path)
                                    rel_path_no_ext = rel_path[:-3] if rel_path.endswith('.md') else rel_path

                                    # Get file modification time
                                    mtime = os.path.getmtime(file_path)
                                    date_str = datetime.fromtimestamp(mtime).strftime('%Y-%m-%d')

                                    # Get first few lines as preview
                                    lines = content.split('\n')
                                    preview = lines[0] if lines else "No preview available"
                                    if len(preview) > 100:
                                        preview = preview[:100] + "..."

                                    results.append({
                                        'file': file,
                                        'path': file_path,
                                        'rel_path': rel_path,
                                        'title': file[:-3],
                                        'preview': preview,
                                        'date': date_str,
                                        'mtime': mtime
                                    })
                        except Exception as e:
                            continue

            # Sort by relevance and modification time
            results.sort(key=lambda x: (0 if query_lower in x['title'].lower() else 1, -x['mtime']))
            return results[:limit]

        except:
            return []

    def create_daily_note(self, vault_path, title=None):
        """Create a daily note in the configured daily notes folder"""
        # Read Obsidian's daily notes configuration
        daily_config = self.get_daily_notes_config(vault_path)

        if not title:
            today = datetime.now()
            # Use the format from Obsidian configuration
            if daily_config and 'format' in daily_config:
                obsidian_format = daily_config['format']
                python_format = self.obsidian_to_python_format(obsidian_format)
                title = today.strftime(python_format)
            else:
                title = today.strftime('%Y-%m-%d')

        # Use the folder from Obsidian configuration
        if daily_config and 'folder' in daily_config:
            daily_folder = daily_config['folder']
        else:
            daily_folder = "Daily"

        daily_path = os.path.join(vault_path, daily_folder)

        # Ensure the daily notes folder exists
        os.makedirs(daily_path, exist_ok=True)

        # Sort existing daily notes in ascending order
        self.sort_daily_notes_folder(daily_path)

        # Create the daily note with template content
        return self.create_daily_note_with_template(vault_path, daily_path, title, daily_config)

    def create_daily_note_with_template(self, vault_path, daily_path, title, daily_config):
        """Create daily note using the configured template"""
        full_path = os.path.join(daily_path, f"{title}.md")

        # Check if note already exists
        if os.path.exists(full_path):
            rel_path = os.path.relpath(full_path, vault_path)
            return full_path, rel_path

        try:
            content = ""

            # Try to use template from configuration
            if daily_config and 'template' in daily_config:
                # Try with .md extension first, then without
                template_paths = [
                    os.path.join(vault_path, daily_config['template'] + '.md'),
                    os.path.join(vault_path, daily_config['template'])
                ]

                template_found = False
                for template_path in template_paths:
                    if os.path.exists(template_path):
                        with open(template_path, 'r', encoding='utf-8') as f:
                            template_content = f.read()

                        # Replace template variables with actual values
                        content = self.process_template(template_content, title)
                        template_found = True
                        break

            # If no template or template not found, use default content
            if not content:
                content = f"# {title}\n\n"
                content += f"Date: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n\n"
                content += "## Notes\n\n"
                content += "- \n\n"

            # Write the note
            with open(full_path, 'w', encoding='utf-8') as f:
                f.write(content)

            rel_path = os.path.relpath(full_path, vault_path)
            return full_path, rel_path

        except Exception as e:
            return None, None

    def process_template(self, template_content, title):
        """Process template content with variable substitution"""
        # Common template variables in Obsidian
        variables = {
            '{{title}}': title,
            '{{date}}': datetime.now().strftime('%Y-%m-%d'),
            '{{time}}': datetime.now().strftime('%H:%M'),
            '{{date:YYYY-MM-DD}}': datetime.now().strftime('%Y-%m-%d'),
            '{{date:MMM DD YYYY}}': datetime.now().strftime('%b %d %Y'),
        }

        content = template_content
        for var, value in variables.items():
            content = content.replace(var, value)

        return content

    def create_daily_note_in_vault(self, vault_path):
        """Create daily note in a specific vault"""
        # Find vault name for the response
        vault_name = "Unknown Vault"
        for vault in self.vaults:
            if vault['path'] == vault_path:
                vault_name = vault['name']
                break

        note_path, rel_path = self.create_daily_note(vault_path)

        if note_path:
            # Open the note directly
            self.open_note(note_path)

            # Return success message
            return [{
                "Title": f"✅ Daily Note Created in {vault_name}",
                "SubTitle": f"📁 {vault_name}/{rel_path} - Opened in Obsidian",
                "IcoPath": "obsidian_icon.png"
            }]
        else:
            return [{
                "Title": "❌ Failed to create daily note",
                "SubTitle": "Check vault permissions and template path",
                "IcoPath": "obsidian_icon.png"
            }]

    def obsidian_to_python_format(self, obsidian_format):
        """Convert Obsidian date format to Python strftime format"""
        # Obsidian format codes to Python format codes
        # We need to replace longer codes first to avoid partial replacements
        format_mapping = [
            ('YYYY', '%Y'),
            ('YY', '%y'),
            ('MMMM', '%B'),
            ('MMM', '%b'),
            ('MM', '%m'),
            ('DD', '%d'),
            ('D', '%-d' if platform.system() != 'Windows' else '%#d'),
            ('dddd', '%A'),
            ('ddd', '%a'),
            ('ww', '%U'),
            ('w', '%W')
        ]

        python_format = obsidian_format
        for obsidian_code, python_code in format_mapping:
            python_format = python_format.replace(obsidian_code, python_code)

        return python_format

    def get_daily_notes_config(self, vault_path):
        """Get the daily notes configuration from Obsidian vault"""
        config_path = os.path.join(vault_path, '.obsidian', 'daily-notes.json')
        if os.path.exists(config_path):
            try:
                with open(config_path, 'r', encoding='utf-8') as f:
                    return json.load(f)
            except:
                pass
        return None

    def sort_daily_notes_folder(self, daily_folder_path):
        """Sort daily notes folder in ascending order (chronological)"""
        if not os.path.exists(daily_folder_path):
            return

        try:
            # Get all markdown files in the daily folder
            files = []
            for filename in os.listdir(daily_folder_path):
                if filename.endswith('.md'):
                    filepath = os.path.join(daily_folder_path, filename)
                    if os.path.isfile(filepath):
                        files.append((filename, filepath))

            if not files:
                return

            # Sort by filename (which are dates in YYYY-MM-DD format)
            files.sort(key=lambda x: x[0])

            # The files are already in the correct order since they're sorted by name
            # Windows Explorer will show them in this order
            # If we wanted to physically reorder files, we'd need to rename them
            # But that's not necessary since the date format already sorts chronologically

        except Exception as e:
            pass

    def create_new_note(self, vault_path, title):
        """Create a new note with the given title"""
        # Sanitize title for filename
        filename = re.sub(r'[<>:"/\\|?*]', '_', title)
        full_path = os.path.join(vault_path, f"{filename}.md")

        # Handle duplicate names
        counter = 1
        while os.path.exists(full_path):
            full_path = os.path.join(vault_path, f"{filename} {counter}.md")
            counter += 1

        try:
            with open(full_path, 'w', encoding='utf-8') as f:
                f.write(f"# {title}\n\n")
                f.write(f"Created: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n\n")
                f.write("## Content\n\n")
                f.write("- \n\n")

            rel_path = os.path.relpath(full_path, vault_path)
            return full_path, rel_path
        except:
            return None, None

    def open_note(self, note_path):
        """Open a note in Obsidian"""
        try:
            # Get vault path and relative path
            vault_path = None
            for vault in self.vaults:
                if note_path.startswith(vault['path']):
                    vault_path = vault['path']
                    break

            if vault_path:
                rel_path = os.path.relpath(note_path, vault_path)
                vault_name = os.path.basename(vault_path)

                # Create Obsidian URI
                uri = f"obsidian://open?vault={urllib.parse.quote(vault_name)}&file={urllib.parse.quote(rel_path)}"
                webbrowser.open(uri)
                return True
            else:
                # Fallback: open file in default editor
                if platform.system() == 'Windows':
                    os.startfile(note_path)
                elif platform.system() == 'Darwin':
                    subprocess.run(['open', note_path])
                else:
                    subprocess.run(['xdg-open', note_path])
                return True
        except:
            return False

    def show_vaults(self):
        """Show all available vaults"""
        results = []
        for vault in self.vaults:
            info = self.get_vault_info(vault['path'])
            results.append({
                "Title": f"📁 {vault['name']}",
                "SubTitle": f"{info['note_count']} notes • {vault['path']}",
                "IcoPath": "obsidian_icon.png",
                "JsonRPCAction": {
                    "method": "open_vault",
                    "parameters": [vault['path']]
                }
            })
        return results

    def show_commands(self):
        """Show available commands"""
        commands = [
            {"emoji": "📁", "command": "vaults", "description": "Show all available vaults"},
            {"emoji": "🔍", "command": "search", "description": "Search notes (usage: obs search [query])"},
            {"emoji": "📝", "command": "new", "description": "Create new note (usage: obs new [title])"},
            {"emoji": "📅", "command": "daily", "description": "Create/open daily note"},
            {"emoji": "🕐", "command": "recent", "description": "Show recent notes"},
            {"emoji": "📂", "command": "vault", "description": "Open specific vault (usage: obs vault [name])"},
            {"emoji": "🚀", "command": "open", "description": "Open Obsidian"}
        ]

        results = []
        for cmd in commands:
            results.append({
                "Title": f"{cmd['emoji']} obs {cmd['command']}",
                "SubTitle": cmd['description'],
                "IcoPath": "obsidian_icon.png",
                "JsonRPCAction": {
                    "method": "execute_command",
                    "parameters": [cmd['command']]
                }
            })

        return results

    def refresh_vaults_cache(self):
        """Refresh vaults cache if needed"""
        current_time = time.time()
        if current_time - self.cache_timestamp > self.cache_duration:
            self.vaults = self.find_vaults()

    def query(self, query_str):
        """Main query handler - similar to Steam plugin's automatic discovery"""
        if isinstance(query_str, list):
            query_str = ' '.join(str(x) for x in query_str)
        elif query_str is None:
            query_str = ""
        else:
            query_str = str(query_str).strip()

        # Refresh vaults cache to ensure we have latest
        self.refresh_vaults_cache()

        parts = query_str.split() if query_str else []
        if not parts:
            # Show main interface with automatic vault discovery (like Steam)
            obsidian_status = "🟢 Running" if self.is_obsidian_running() else "🔴 Not Running"
            vault_count = len(self.vaults)

            results = [
                {
                    "Title": f"📔 Obsidian Notes ({obsidian_status})",
                    "SubTitle": f"{vault_count} vault{'s' if vault_count != 1 else ''} found • Click to see commands",
                    "IcoPath": "obsidian_icon.png",
                    "JsonRPCAction": {
                        "method": "show_commands",
                        "parameters": []
                    }
                }
            ]

            # Show recent vaults and notes (like Steam shows recent games)
            if self.vaults:
                results.append({
                    "Title": f"📁 Open Vaults",
                    "SubTitle": f"Show all {vault_count} available vault{'s' if vault_count != 1 else ''}",
                    "IcoPath": "obsidian_icon.png",
                    "JsonRPCAction": {
                        "method": "show_vaults",
                        "parameters": []
                    }
                })

                # Show top vaults with note counts
                for vault in self.vaults[:5]:  # Show top 5 vaults
                    note_count = vault.get('note_count', 0)
                    results.append({
                        "Title": f"📁 {vault['name']}",
                        "SubTitle": f"{note_count} notes • {vault['path']}",
                        "IcoPath": "obsidian_icon.png",
                        "JsonRPCAction": {
                            "method": "open_vault",
                            "parameters": [vault['path']]
                        }
                    })

            return results

        first_word = parts[0].lower()
        args = " ".join(parts[1:]) if len(parts) > 1 else ""

        if first_word in self.known_commands:
            command = first_word

            if command == "vaults":
                return self.show_vaults()

            elif command == "search":
                if args and self.vaults:
                    all_results = []
                    for vault in self.vaults:
                        search_results = self.search_notes(vault['path'], args, 5)
                        for result in search_results:
                            all_results.append({
                                "Title": f"📝 {result['title']}",
                                "SubTitle": f"📁 {vault['name']} • {result['date']} • {result['preview']}",
                                "IcoPath": "obsidian_icon.png",
                                "JsonRPCAction": {
                                    "method": "open_note",
                                    "parameters": [result['path']]
                                }
                            })
                    return all_results if all_results else [{
                        "Title": f"🔍 No results for '{args}'",
                        "SubTitle": "Try different keywords",
                        "IcoPath": "obsidian_icon.png"
                    }]
                else:
                    return [{
                        "Title": "🔍 Search Notes",
                        "SubTitle": "Usage: obs search [query]",
                        "IcoPath": "obsidian_icon.png"
                    }]

            elif command == "new":
                if args and self.vaults:
                    vault = self.vaults[0]  # Use first vault as default
                    note_path, rel_path = self.create_new_note(vault['path'], args)
                    if note_path:
                        return [{
                            "Title": f"✅ Note Created: {args}",
                            "SubTitle": f"📁 {vault['name']}/{rel_path}",
                            "IcoPath": "obsidian_icon.png",
                            "JsonRPCAction": {
                                "method": "open_note",
                                "parameters": [note_path]
                            }
                        }]
                    else:
                        return [{
                            "Title": "❌ Failed to create note",
                            "SubTitle": "Check vault permissions",
                            "IcoPath": "obsidian_icon.png"
                        }]
                else:
                    return [{
                        "Title": "📝 Create New Note",
                        "SubTitle": "Usage: obs new [title]",
                        "IcoPath": "obsidian_icon.png"
                    }]

            elif command == "daily":
                if self.vaults:
                    if len(self.vaults) == 1:
                        # Single vault - create directly
                        vault = self.vaults[0]
                        note_path, rel_path = self.create_daily_note(vault['path'])
                        if note_path:
                            return [{
                                "Title": f"✅ Daily Note Created",
                                "SubTitle": f"📁 {vault['name']}/{rel_path}",
                                "IcoPath": "obsidian_icon.png",
                                "JsonRPCAction": {
                                    "method": "open_note",
                                    "parameters": [note_path]
                                }
                            }]
                        else:
                            return [{
                                "Title": "❌ Failed to create daily note",
                                "SubTitle": "Check vault permissions",
                                "IcoPath": "obsidian_icon.png"
                            }]
                    else:
                        # Multiple vaults - show options
                        results = [{
                            "Title": "📅 Create Daily Note In:",
                            "SubTitle": f"Choose which vault to create today's daily note in",
                            "IcoPath": "obsidian_icon.png"
                        }]

                        for vault in self.vaults:
                            results.append({
                                "Title": f"📝 {vault['name']}",
                                "SubTitle": f"Create daily note in {vault['name']} vault",
                                "IcoPath": "obsidian_icon.png",
                                "JsonRPCAction": {
                                    "method": "create_daily_note_in_vault",
                                    "parameters": [vault['path']]
                                }
                            })

                        return results
                else:
                    return [{
                        "Title": "❌ No vaults found",
                        "SubTitle": "Create an Obsidian vault first",
                        "IcoPath": "obsidian_icon.png"
                    }]

            elif command == "vault":
                if args:
                    for vault in self.vaults:
                        if vault['name'].lower().find(args.lower()) >= 0:
                            return [{
                                "Title": f"📁 Open {vault['name']}",
                                "SubTitle": f"Open vault: {vault['path']}",
                                "IcoPath": "obsidian_icon.png",
                                "JsonRPCAction": {
                                    "method": "open_vault",
                                    "parameters": [vault['path']]
                                }
                            }]
                    return [{
                        "Title": f"❌ Vault not found: {args}",
                        "SubTitle": "Use 'obs vaults' to see available vaults",
                        "IcoPath": "obsidian_icon.png"
                    }]
                else:
                    return self.show_vaults()

            elif command == "open":
                return [{
                    "Title": "🚀 Launch Obsidian",
                    "SubTitle": "Open Obsidian application",
                    "IcoPath": "obsidian_icon.png",
                    "JsonRPCAction": {
                        "method": "launch_obsidian",
                        "parameters": []
                    }
                }]

            elif command == "recent":
                if self.vaults:
                    vault = self.vaults[0]  # Use first vault
                    info = self.get_vault_info(vault['path'])
                    results = []
                    for note_path, mtime in info['recent_notes'][:5]:
                        note_name = os.path.basename(note_path)[:-3]  # Remove .md
                        date_str = datetime.fromtimestamp(mtime).strftime('%Y-%m-%d')
                        rel_path = os.path.relpath(note_path, vault['path'])

                        results.append({
                            "Title": f"🕐 {note_name}",
                            "SubTitle": f"📁 {vault['name']} • {date_str}",
                            "IcoPath": "obsidian_icon.png",
                            "JsonRPCAction": {
                                "method": "open_note",
                                "parameters": [note_path]
                            }
                        })
                    return results if results else [{
                        "Title": "❌ No recent notes found",
                        "SubTitle": "Start creating notes in your vault",
                        "IcoPath": "obsidian_icon.png"
                    }]
                else:
                    return [{
                        "Title": "❌ No vaults found",
                        "SubTitle": "Create an Obsidian vault first",
                        "IcoPath": "obsidian_icon.png"
                    }]

        else:
            # General search across all vaults
            if self.vaults:
                all_results = []
                for vault in self.vaults:
                    search_results = self.search_notes(vault['path'], query_str, 3)
                    for result in search_results:
                        all_results.append({
                            "Title": f"📝 {result['title']}",
                            "SubTitle": f"📁 {vault['name']} • {result['date']}",
                            "IcoPath": "obsidian_icon.png",
                            "JsonRPCAction": {
                                "method": "open_note",
                                "parameters": [result['path']]
                            }
                        })

                if all_results:
                    return all_results[:10]  # Limit to 10 results
                else:
                    return [{
                        "Title": f"🔍 No notes found for '{query_str}'",
                        "SubTitle": "Try different keywords or create a new note",
                        "IcoPath": "obsidian_icon.png"
                    }]
            else:
                return [{
                    "Title": "❌ No vaults found",
                    "SubTitle": "Create an Obsidian vault first",
                    "IcoPath": "obsidian_icon.png"
                }]

    def execute_command(self, command, value=None):
        """Execute command and return confirmation"""
        if command == "launch_obsidian":
            success = self.launch_obsidian()
            if success:
                return [{
                    "Title": "✅ Obsidian Launched",
                    "SubTitle": "Obsidian is now running",
                    "IcoPath": "obsidian_icon.png"
                }]
            else:
                return [{
                    "Title": "❌ Failed to launch Obsidian",
                    "SubTitle": "Check if Obsidian is installed",
                    "IcoPath": "obsidian_icon.png"
                }]

        return [{
            "Title": f"✅ Command Executed: {command}",
            "SubTitle": f"Executed {command} command",
            "IcoPath": "obsidian_icon.png"
        }]

    def open_vault(self, vault_path):
        """Open a specific vault"""
        success = self.launch_obsidian(vault_path)
        vault_name = os.path.basename(vault_path)

        if success:
            return [{
                "Title": f"✅ Opened Vault: {vault_name}",
                "SubTitle": f"Vault path: {vault_path}",
                "IcoPath": "obsidian_icon.png"
            }]
        else:
            return [{
                "Title": f"❌ Failed to open vault: {vault_name}",
                "SubTitle": "Check vault path and permissions",
                "IcoPath": "obsidian_icon.png"
            }]

def main():
    """Main entry point"""
    plugin = ObsidianPlugin()

    try:
        if len(sys.argv) > 1:
            request = json.loads(sys.argv[1])
            method = request.get("method", "")
            parameters = request.get("parameters", [])

            if method == "query":
                query_param = parameters if parameters else ""
                results = plugin.query(query_param)
                print(json.dumps({"result": results}))

            elif method == "show_commands":
                commands_results = plugin.show_commands()
                print(json.dumps({"result": commands_results}))

            elif method == "show_vaults":
                vaults_results = plugin.show_vaults()
                print(json.dumps({"result": vaults_results}))

            elif method == "execute_command":
                command = parameters[0] if parameters else ""
                value = parameters[1] if len(parameters) > 1 else None
                command_results = plugin.execute_command(command, value)
                print(json.dumps({"result": command_results}))

            elif method == "open_vault":
                vault_path = parameters[0] if parameters else ""
                vault_results = plugin.open_vault(vault_path)
                print(json.dumps({"result": vault_results}))

            elif method == "open_note":
                note_path = parameters[0] if parameters else ""
                success = plugin.open_note(note_path)
                result = [{
                    "Title": "✅ Note Opened" if success else "❌ Failed to open note",
                    "SubTitle": os.path.basename(note_path) if success else "Check note path",
                    "IcoPath": "obsidian_icon.png"
                }]
                print(json.dumps({"result": result}))

            elif method == "create_daily_note_in_vault":
                vault_path = parameters[0] if parameters else ""
                result = plugin.create_daily_note_in_vault(vault_path)
                print(json.dumps({"result": result}))

            elif method == "launch_obsidian":
                launch_results = plugin.execute_command("launch_obsidian")
                print(json.dumps({"result": launch_results}))

            elif hasattr(plugin, method):
                method_func = getattr(plugin, method)
                if parameters:
                    result = method_func(*parameters)
                else:
                    result = method_func()
                print(json.dumps({"result": result}))
        else:
            results = plugin.query("")
            print(json.dumps({"result": results}))

    except Exception as e:
        error_result = [{
            "Title": "Obsidian Plugin Error",
            "SubTitle": f"Error: {str(e)}",
            "IcoPath": "obsidian_icon.png"
        }]
        print(json.dumps({"result": error_result}))

if __name__ == "__main__":
    main()