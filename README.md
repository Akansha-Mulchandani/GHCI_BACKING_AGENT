# ADK Banking Voice Agent

A sophisticated multi-agent banking system powered by Google's Agent Development Kit (ADK) and Gemini 2.0 Flash. The system handles user authentication, account management, transactions, and loan processing through natural voice conversations.

## Overview

### What is ADK?

The **Agent Development Kit (ADK)** is Google's framework for building AI agents that can take actions through tools. Unlike traditional chatbots, ADK agents are:
- **Tool-enabled**: Agents have explicit tools they can call to perform real actions
- **Stateful**: Agents maintain context across conversations
- **Autonomous**: Agents can reason through problems and take multiple steps
- **Multi-agent ready**: Multiple specialized agents can work together

### Architecture

This project uses a **multi-agent orchestrator pattern**:
- **Banking Agent** (Orchestrator): Routes user requests to appropriate sub-agents
- **Verification Agent**: Handles user authentication via SMS OTP (Twilio Verify)
- **Transaction Agent**: Manages balance queries, fund transfers, and transaction history
- **Loan Agent**: Processes loan applications, eligibility checks, and EMI calculations

Each agent has specialized tools and operates independently, enabling scalable and maintainable code.

## Features

- 🔐 **Twilio-based SMS OTP Authentication**: Secure user verification via SMS
- 💰 **Account Management**: Create accounts, check balances, view transaction history
- 💸 **Fund Transfers**: Send money between accounts with proper validation
- 📊 **Loan Management**: Check eligibility, apply for loans, calculate EMI
- 🎤 **Voice Interface**: Natural language voice conversations with WebSocket streaming
- 🗄️ **Persistent Storage**: PostgreSQL database for all user and transaction data
- 🔄 **Session Management**: Multi-session support with token-based authentication
- 🔔 **Alerts & Notifications**: Real-time alerts for transactions, low balance warnings, and loan updates

## Technology Stack

- **Framework**: Google ADK with Gemini 2.0 Flash
- **Backend**: FastAPI with WebSocket support
- **Database**: PostgreSQL with SQLAlchemy ORM
- **Authentication**: Twilio Verify (SMS OTP)
- **Voice**: PCM audio streaming over WebSocket

## Why Google ADK Over Traditional Applications?

Traditional banking applications rely on rigid, rule-based logic. ADK transforms this with:

| Aspect | Traditional Apps | ADK Framework |
|--------|-----------------|---------------|
| **Decision Making** | Fixed if-else chains | Intelligent reasoning with context awareness |
| **Scalability** | Adding features requires code changes | New tools automatically integrated |
| **User Experience** | Rigid conversation flows | Natural, adaptive dialogue |
| **Multi-tasking** | Single purpose per function | Multiple agents collaborate on complex tasks |
| **Error Handling** | Predetermined error messages | Agents reason about problems and adapt |
| **Learning** | Manual updates required | Agents learn from tool feedback |

ADK enables a **conversation-driven banking experience** where the system understands user intent, delegates to specialized agents, and delivers intelligent, context-aware responses—all without explicit programming for every scenario.
