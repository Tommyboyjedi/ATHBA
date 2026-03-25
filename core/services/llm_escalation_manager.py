"""
LLM Escalation Manager service.

This module manages LLM tier escalation based on failure counts for
Developer and Tester agents independently. Implements 3-failure escalation:
- STANDARD → HEAVY (after 3 failures)
- HEAVY → MEGA (after 3 more failures)
"""

from typing import Tuple
from llm_service.enums.etier import ETier
from core.dataclasses.ticket_model import TicketModel
from core.dataclasses.history_entry import HistoryEntry
from core.datastore.repos.ticket_repo import TicketRepo
from datetime import datetime


class LlmEscalationManager:
    """
    Manages LLM tier escalation for Developer and Tester agents.
    
    Tracks failure counts independently for each agent and escalates
    through tiers (STANDARD → HEAVY → MEGA) after 3 consecutive failures.
    Resets count on success.
    
    Attributes:
        ticket_repo: Repository for ticket operations
        max_failures_per_tier: Number of failures before escalating (default: 3)
    """
    
    def __init__(self, max_failures_per_tier: int = 3):
        """
        Initialize the LLM Escalation Manager.
        
        Args:
            max_failures_per_tier: Number of consecutive failures before
                                  escalating to next tier (default: 3)
        """
        self.ticket_repo = TicketRepo()
        self.max_failures_per_tier = max_failures_per_tier
    
    async def record_failure(
        self, 
        ticket: TicketModel, 
        agent_type: str,
        reason: str
    ) -> Tuple[TicketModel, ETier]:
        """
        Record a failure for an agent and potentially escalate LLM tier.
        
        Args:
            ticket: The ticket being worked on
            agent_type: Either "Developer" or "Tester"
            reason: Description of the failure
            
        Returns:
            Tuple of (updated_ticket, new_tier)
            
        Raises:
            ValueError: If agent_type is not "Developer" or "Tester"
        """
        if agent_type not in ["Developer", "Tester"]:
            raise ValueError(f"Invalid agent_type: {agent_type}")
        
        # Increment failure count
        if agent_type == "Developer":
            ticket.developer_failure_count += 1
            failure_count = ticket.developer_failure_count
            current_tier_str = ticket.developer_llm_tier
        else:  # Tester
            ticket.tester_failure_count += 1
            failure_count = ticket.tester_failure_count
            current_tier_str = ticket.tester_llm_tier
        
        # Determine new tier based on failure count
        new_tier = self._calculate_tier(failure_count)
        new_tier_str = new_tier.value
        
        # Check if tier changed
        tier_changed = new_tier_str != current_tier_str
        
        # Update ticket tier
        if agent_type == "Developer":
            ticket.developer_llm_tier = new_tier_str
        else:
            ticket.tester_llm_tier = new_tier_str
        
        # Add history entry
        history_msg = (
            f"{agent_type} failure #{failure_count}: {reason}. "
        )
        if tier_changed:
            history_msg += f"Escalated to {new_tier_str.upper()} tier."
        else:
            history_msg += f"Remaining on {new_tier_str.upper()} tier."
        
        ticket.history.append(HistoryEntry(
            timestamp=datetime.utcnow(),
            agent=agent_type,
            action="llm_escalation",
            details=history_msg
        ))
        
        ticket.updated_at = datetime.utcnow()
        
        # Save to database
        await self.ticket_repo.update(ticket)
        
        return ticket, new_tier
    
    async def record_success(
        self, 
        ticket: TicketModel, 
        agent_type: str
    ) -> TicketModel:
        """
        Record a success for an agent and reset failure count.
        
        Resets failure count to 0 and tier back to STANDARD.
        
        Args:
            ticket: The ticket being worked on
            agent_type: Either "Developer" or "Tester"
            
        Returns:
            Updated ticket
            
        Raises:
            ValueError: If agent_type is not "Developer" or "Tester"
        """
        if agent_type not in ["Developer", "Tester"]:
            raise ValueError(f"Invalid agent_type: {agent_type}")
        
        # Get old values for logging
        if agent_type == "Developer":
            old_count = ticket.developer_failure_count
            old_tier = ticket.developer_llm_tier
            ticket.developer_failure_count = 0
            ticket.developer_llm_tier = "standard"
        else:  # Tester
            old_count = ticket.tester_failure_count
            old_tier = ticket.tester_llm_tier
            ticket.tester_failure_count = 0
            ticket.tester_llm_tier = "standard"
        
        # Add history entry if there were previous failures
        if old_count > 0:
            history_msg = (
                f"{agent_type} success! Reset failure count from {old_count} to 0. "
                f"Tier reset to STANDARD (was {old_tier.upper()})."
            )
            ticket.history.append(HistoryEntry(
                timestamp=datetime.utcnow(),
                agent=agent_type,
                action="llm_escalation_reset",
                details=history_msg
            ))
            
            ticket.updated_at = datetime.utcnow()
            
            # Save to database
            await self.ticket_repo.update(ticket)
        
        return ticket
    
    def _calculate_tier(self, failure_count: int) -> ETier:
        """
        Calculate the appropriate LLM tier based on failure count.
        
        Args:
            failure_count: Number of consecutive failures
            
        Returns:
            ETier enum value (STANDARD, HEAVY, or MEGA)
        """
        if failure_count < self.max_failures_per_tier:
            return ETier.STANDARD
        elif failure_count < self.max_failures_per_tier * 2:
            return ETier.HEAVY
        else:
            return ETier.MEGA
    
    def get_current_tier(self, ticket: TicketModel, agent_type: str) -> ETier:
        """
        Get the current LLM tier for an agent on a ticket.
        
        Args:
            ticket: The ticket being worked on
            agent_type: Either "Developer" or "Tester"
            
        Returns:
            Current ETier for the agent
            
        Raises:
            ValueError: If agent_type is not "Developer" or "Tester"
        """
        if agent_type not in ["Developer", "Tester"]:
            raise ValueError(f"Invalid agent_type: {agent_type}")
        
        if agent_type == "Developer":
            tier_str = ticket.developer_llm_tier
        else:
            tier_str = ticket.tester_llm_tier
        
        # Convert string to ETier enum
        return ETier(tier_str)
