#!/usr/bin/env python3
"""
UCLI Registry Version Updater

Fetches latest commit hashes for all official UCLI tools and updates the registry
with precise commit-based versioning for reproducible builds.

Usage:
    python update-versions.py [--dry-run] [--verbose]

Options:
    --dry-run    Show what would be changed without modifying files
    --verbose    Show detailed output
"""

import argparse
import json
import re
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, List, Optional, Tuple
from urllib.request import urlopen
from urllib.error import URLError

import yaml


class RegistryUpdater:
    def __init__(self, dry_run: bool = False, verbose: bool = False):
        self.dry_run = dry_run
        self.verbose = verbose
        self.registry_file = Path(__file__).parent.parent / "registry" / "apps.yaml"

    def log(self, message: str) -> None:
        """Log message if verbose mode is enabled."""
        if self.verbose:
            print(f"[INFO] {message}")

    def error(self, message: str) -> None:
        """Log error message."""
        print(f"[ERROR] {message}", file=sys.stderr)

    def get_github_commit_info(self, repo_url: str) -> Optional[Dict]:
        """
        Fetch latest commit information from GitHub API.

        Args:
            repo_url: GitHub repository URL (e.g., 'github.com/ucli-tools/gits')

        Returns:
            Dict with commit hash, date, and message, or None if failed
        """
        try:
            # Extract owner/repo from URL
            match = re.match(r"github\.com/([^/]+)/([^/]+)", repo_url)
            if not match:
                self.error(f"Invalid GitHub URL format: {repo_url}")
                return None

            owner, repo = match.groups()

            # GitHub API URL for latest commit on default branch
            api_url = f"https://api.github.com/repos/{owner}/{repo}/commits?per_page=1"

            self.log(f"Fetching latest commit for {owner}/{repo}")

            with urlopen(api_url) as response:
                data = json.loads(response.read().decode())

            if not data:
                self.error(f"No commits found for {owner}/{repo}")
                return None

            commit = data[0]
            commit_hash = commit['sha']
            commit_date = commit['commit']['committer']['date']
            commit_message = commit['commit']['message'].split('\n')[0]  # First line only

            # Parse and format date
            parsed_date = datetime.fromisoformat(commit_date.replace('Z', '+00:00'))
            formatted_date = parsed_date.strftime('%Y-%m-%d %H:%M:%S UTC')

            return {
                'hash': commit_hash,
                'short_hash': commit_hash[:8],
                'date': formatted_date,
                'message': commit_message,
                'url': f"https://github.com/{owner}/{repo}/commit/{commit_hash}"
            }

        except URLError as e:
            self.error(f"Network error fetching {repo_url}: {e}")
            return None
        except json.JSONDecodeError as e:
            self.error(f"JSON parsing error for {repo_url}: {e}")
            return None
        except Exception as e:
            self.error(f"Unexpected error fetching {repo_url}: {e}")
            return None

    def update_app_version(self, app: Dict) -> Tuple[bool, str]:
        """
        Update a single app's version information.

        Args:
            app: App dictionary from registry

        Returns:
            Tuple of (updated: bool, message: str)
        """
        repo_url = app.get('repo', '')
        current_version = app.get('version', '')

        if not repo_url:
            return False, "No repository URL specified"

        commit_info = self.get_github_commit_info(repo_url)
        if not commit_info:
            return False, "Failed to fetch commit information"

        new_version = commit_info['hash']

        if current_version == new_version:
            return False, f"Already at latest version {commit_info['short_hash']}"

        # Update app with new version info
        app['version'] = new_version

        # Add additional metadata
        if 'version_info' not in app:
            app['version_info'] = {}

        app['version_info'].update({
            'commit_date': commit_info['date'],
            'commit_message': commit_info['message'],
            'commit_url': commit_info['url'],
            'updated_at': datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M:%S UTC')
        })

        short_hash = commit_info['short_hash']
        message = commit_info['message'][:50] + ('...' if len(commit_info['message']) > 50 else '')

        return True, f"Updated to {short_hash}: {message}"

    def load_registry(self) -> Optional[Dict]:
        """Load the registry YAML file."""
        try:
            with open(self.registry_file, 'r', encoding='utf-8') as f:
                return yaml.safe_load(f)
        except FileNotFoundError:
            self.error(f"Registry file not found: {self.registry_file}")
            return None
        except yaml.YAMLError as e:
            self.error(f"Error parsing YAML: {e}")
            return None

    def save_registry(self, registry: Dict) -> bool:
        """Save the registry YAML file."""
        try:
            # Update metadata
            registry['metadata']['last_updated'] = datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M:%S UTC')

            if not self.dry_run:
                with open(self.registry_file, 'w', encoding='utf-8') as f:
                    yaml.safe_dump(registry, f, default_flow_style=False, sort_keys=False,
                                 allow_unicode=True, indent=2)

            return True
        except Exception as e:
            self.error(f"Error saving registry: {e}")
            return False

    def update_all_versions(self) -> bool:
        """Update version information for all official apps."""
        print("🔄 UCLI Registry Version Updater")
        print("=" * 50)

        registry = self.load_registry()
        if not registry:
            return False

        official_apps = registry.get('apps', {}).get('official', [])
        if not official_apps:
            self.error("No official apps found in registry")
            return False

        print(f"📦 Found {len(official_apps)} official tools")
        print()

        updated_count = 0
        failed_count = 0

        for app in official_apps:
            app_name = app.get('name', 'unknown')
            print(f"🔍 Checking {app_name}...")

            updated, message = self.update_app_version(app)

            if updated:
                print(f"  ✅ {message}")
                updated_count += 1
            else:
                print(f"  ⏭️  {message}")

            print()

        # Save registry
        if updated_count > 0:
            if self.save_registry(registry):
                print(f"💾 Registry saved successfully")
            else:
                print(f"❌ Failed to save registry")
                return False
        else:
            print(f"📋 No updates needed")

        print()
        print("📊 Summary:")
        print(f"  • Tools checked: {len(official_apps)}")
        print(f"  • Updated: {updated_count}")
        print(f"  • Failed: {failed_count}")
        print(f"  • Mode: {'DRY RUN' if self.dry_run else 'LIVE UPDATE'}")

        return True


def main():
    parser = argparse.ArgumentParser(
        description="Update UCLI Registry with latest commit hashes for reproducible builds"
    )
    parser.add_argument(
        '--dry-run',
        action='store_true',
        help='Show what would be changed without modifying files'
    )
    parser.add_argument(
        '--verbose', '-v',
        action='store_true',
        help='Show detailed output'
    )

    args = parser.parse_args()

    updater = RegistryUpdater(dry_run=args.dry_run, verbose=args.verbose)
    success = updater.update_all_versions()

    sys.exit(0 if success else 1)


if __name__ == '__main__':
    main()
