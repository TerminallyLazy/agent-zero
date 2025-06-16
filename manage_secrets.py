#!/usr/bin/env python3
"""
Agent Zero Secrets Management CLI
Command-line utility for managing the placeholder-based secrets system.
"""

import sys
import os
import argparse
from pathlib import Path

# Add the project root to Python path
sys.path.insert(0, str(Path(__file__).parent))

from python.helpers.secrets import SecretsManager
from python.helpers.secrets_migration import SecretsMigration
from python.helpers.print_style import PrintStyle


def cmd_migrate(args):
    """Migrate from .env to placeholder system"""
    print("🔄 Starting migration from .env to placeholder system...")
    
    migrated, placeholders = SecretsMigration.migrate_to_placeholder_system(force=args.force)
    
    if migrated > 0 or placeholders > 0:
        print(f"✅ Migration complete: {migrated} secrets migrated, {placeholders} placeholders created")
    else:
        print("✅ No migration needed - system already up to date")


def cmd_sync(args):
    """Synchronize .env and secrets.env files"""
    print("🔄 Synchronizing .env and secrets.env files...")
    
    report = SecretsMigration.sync_env_and_secrets()
    
    if report["status"] == "success":
        if report["secrets_found"] > 0:
            print(f"✅ Sync complete: {report['secrets_found']} secrets moved")
        else:
            print("✅ Files already synchronized")
    else:
        print(f"❌ Sync failed: {report.get('error', 'Unknown error')}")


def cmd_validate(args):
    """Validate current secrets configuration"""
    print("🔍 Validating secrets configuration...")
    
    validation = SecretsMigration.validate_configuration()
    
    print(f"Status: {validation['status']}")
    print(f".env file exists: {validation['env_file_exists']}")
    print(f"secrets.env exists: {validation['secrets_file_exists']}")
    
    if validation['secrets_file_exists']:
        perms = validation['secrets_file_permissions']
        if perms == '600':
            print(f"✅ File permissions: {perms}")
        else:
            print(f"⚠️ File permissions: {perms} (should be 600)")
    
    if validation['raw_secrets_in_env']:
        print(f"⚠️ Raw secrets in .env: {validation['raw_secrets_in_env']}")
    else:
        print("✅ No raw secrets in .env")
    
    if validation['missing_placeholders']:
        print(f"⚠️ Missing placeholders: {validation['missing_placeholders']}")
    
    if validation['orphaned_secrets']:
        print(f"⚠️ Orphaned placeholders: {validation['orphaned_secrets']}")
    
    if validation['status'] == 'healthy':
        print("🎉 Configuration is healthy!")
    elif validation['status'] == 'migration_needed':
        print("🔄 Run 'python manage_secrets.py migrate' to fix")
    elif validation['status'] == 'sync_needed':
        print("🔄 Run 'python manage_secrets.py sync' to fix")


def cmd_list(args):
    """List current secrets"""
    print("📋 Current secrets:")
    
    secrets = SecretsManager.load_secrets_dict()
    
    if not secrets:
        print("No secrets configured")
        return
    
    for key in sorted(secrets.keys()):
        if args.show_values:
            print(f"  {key}={secrets[key]}")
        else:
            print(f"  {key}=***")


def cmd_add(args):
    """Add a new secret"""
    key = args.key.upper().strip()
    value = args.value
    
    if not value:
        import getpass
        value = getpass.getpass(f"Enter value for {key}: ")
    
    if SecretsManager.save_secret(key, value):
        print(f"✅ Secret {key} saved successfully")
        
        print(f"💡 Add this placeholder to your .env file: {key}=§§{key}§§")
    else:
        print(f"❌ Failed to save secret {key}")


def cmd_remove(args):
    """Remove a secret"""
    key = args.key.upper().strip()
    
    if SecretsManager.delete_secret(key):
        print(f"✅ Secret {key} removed successfully")
        
        print(f"💡 Remove this placeholder from your .env file: {key}=§§{key}§§")
    else:
        print(f"❌ Secret {key} not found")


def cmd_fix_permissions(args):
    """Fix secrets.env file permissions"""
    from python.helpers import files
    
    secrets_path = files.get_abs_path(SecretsManager.SECRETS_FILE)
    
    if not os.path.exists(secrets_path):
        print("❌ secrets.env file does not exist")
        return
    
    try:
        os.chmod(secrets_path, 0o600)
        print("✅ File permissions fixed: 600")
    except Exception as e:
        print(f"❌ Failed to fix permissions: {e}")


def main():
    parser = argparse.ArgumentParser(
        description="Agent Zero Secrets Management CLI",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python manage_secrets.py migrate              # Migrate from .env to placeholder system
  python manage_secrets.py sync                 # Sync .env and secrets.env files
  python manage_secrets.py validate             # Check configuration health
  python manage_secrets.py list                 # List secret keys (values masked)
  python manage_secrets.py list --show-values   # List with actual values
  python manage_secrets.py add API_KEY_TEST     # Add secret (prompts for value)
  python manage_secrets.py add API_KEY_TEST "secret-value"  # Add with value
  python manage_secrets.py remove API_KEY_TEST  # Remove secret
  python manage_secrets.py fix-permissions      # Fix file permissions
        """
    )
    
    subparsers = parser.add_subparsers(dest='command', help='Available commands')
    
    # Migrate command
    migrate_parser = subparsers.add_parser('migrate', help='Migrate from .env to placeholder system')
    migrate_parser.add_argument('--force', action='store_true', 
                               help='Force migration even if not needed')
    
    # Sync command
    subparsers.add_parser('sync', help='Synchronize .env and secrets.env files')
    
    # Validate command
    subparsers.add_parser('validate', help='Validate current configuration')
    
    # List command
    list_parser = subparsers.add_parser('list', help='List current secrets')
    list_parser.add_argument('--show-values', action='store_true',
                            help='Show actual secret values (use with caution)')
    
    # Add command
    add_parser = subparsers.add_parser('add', help='Add a new secret')
    add_parser.add_argument('key', help='Secret key name')
    add_parser.add_argument('value', nargs='?', help='Secret value (optional, will prompt if not provided)')
    
    # Remove command
    remove_parser = subparsers.add_parser('remove', help='Remove a secret')
    remove_parser.add_argument('key', help='Secret key name')
    
    # Fix permissions command
    subparsers.add_parser('fix-permissions', help='Fix secrets.env file permissions')
    
    args = parser.parse_args()
    
    if not args.command:
        parser.print_help()
        return
    
    # Map commands to functions
    commands = {
        'migrate': cmd_migrate,
        'sync': cmd_sync,
        'validate': cmd_validate,
        'list': cmd_list,
        'add': cmd_add,
        'remove': cmd_remove,
        'fix-permissions': cmd_fix_permissions,
    }
    
    if args.command in commands:
        try:
            commands[args.command](args)
        except KeyboardInterrupt:
            print("\n❌ Operation cancelled")
        except Exception as e:
            print(f"❌ Error: {e}")
            if args.command == 'migrate' or args.command == 'sync':
                print("💡 Try running 'python manage_secrets.py validate' to diagnose issues")
    else:
        print(f"❌ Unknown command: {args.command}")
        parser.print_help()


if __name__ == "__main__":
    main()