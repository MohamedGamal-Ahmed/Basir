"""Commands package - Command Pattern for extensible test types.

Provides:
    - BaseTestCommand: Abstract base class for all test commands.
    - LoginTestCommand: Scripted login flow testing (MVP).
    - AutonomousCommand: ReAct-based autonomous goal testing.
"""

from basir.commands.base_command import BaseTestCommand
from basir.commands.login_test import LoginTestCommand
from basir.commands.autonomous_command import AutonomousCommand

__all__ = ["BaseTestCommand", "LoginTestCommand", "AutonomousCommand"]
