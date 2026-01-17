# SkinTwin Ecosystem Integration Mapping

## Repository Relationship Matrix

The following matrix illustrates the dependencies and integration points between repositories in the SkinTwin ecosystem. Each cell indicates the nature of the relationship between the row repository (consumer) and column repository (provider).

| Consumer → Provider | skintwin | skintwin-asi | multiskin | org-skin | customer-portal | regima-lms | integrations | directory-template |
|---------------------|----------|--------------|-----------|----------|-----------------|------------|--------------|-------------------|
| **skintwin** | - | Spec | Spec | - | - | - | - | - |
| **skintwin-asi** | Implements | - | Shares Agents | - | - | - | - | - |
| **multiskin** | Implements | Shares Agents | - | - | - | - | - | - |
| **org-skin** | - | - | - | - | Monitors | Monitors | Monitors | Monitors |
| **customer-portal** | - | Consumes AI | Consumes AI | - | - | Links | Consumes | - |
| **regima-lms** | - | - | - | - | Links | - | Consumes | - |
| **integrations** | - | - | - | - | Provides | Provides | - | - |
| **directory-template** | - | - | - | - | UI Template | - | - | - |

## Integration Points by Domain

### AI/Cognitive Services Integration

The cognitive layer provides intelligent services to business applications through a unified API. The **skintwin** repository defines the Alchemist Engine specification, which both **skintwin-asi** and **multiskin** implement. These implementations share the same cognitive agent architecture (Deep Tree Echo, Marduk, CEO) and can provide skin analysis, personalization, and recommendation services to downstream applications.

The **skintwin-customer-portal** and **regima-training-lms** can consume these AI services for features such as personalized product recommendations, skin concern analysis, and adaptive learning paths.

### Business Application Integration

The **skintwin-customer-portal** serves as the primary business management platform, handling multi-tenant operations for salons, therapists, and retail customers. It integrates with **regima-training-lms** to provide training and certification tracking for therapists. Both applications share common data models for customers, products, and organizations.

The **skintwin-integrations** repository provides the connector layer that enables both applications to communicate with external platforms (Shopify, Wix, OpenCart, payment processors, and accounting systems).

### Frontend Template Integration

The **business-directory-template** provides a reusable UI pattern for business discovery and listing. This template can be integrated into the customer portal as a public-facing directory for finding salons and therapists. The design system (Dark Atlas Interface with Electric Cyan and Amber Gold) can be adopted across all frontend applications for visual consistency.

### DevOps and Organization Management

The **org-skin** repository provides organization-wide GitHub management capabilities. It can monitor all repositories, analyze patterns, and synthesize best practices. This enables automated quality checks, dependency management, and template generation across the ecosystem.

## Data Flow Architecture

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                           EXTERNAL PLATFORMS                                 │
│  ┌──────────┐ ┌──────────┐ ┌──────────┐ ┌──────────┐ ┌──────────┐          │
│  │ Shopify  │ │   Wix    │ │ OpenCart │ │  Stripe  │ │QuickBooks│          │
│  └────┬─────┘ └────┬─────┘ └────┬─────┘ └────┬─────┘ └────┬─────┘          │
└───────┼────────────┼────────────┼────────────┼────────────┼─────────────────┘
        │            │            │            │            │
        ▼            ▼            ▼            ▼            ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│                        INTEGRATION LAYER (skintwin-integrations)             │
│  ┌──────────────┐ ┌──────────────┐ ┌──────────────┐ ┌──────────────┐        │
│  │ Wix Connector│ │Shopify Conn. │ │OpenCart Conn.│ │Payment Conn. │        │
│  └──────────────┘ └──────────────┘ └──────────────┘ └──────────────┘        │
│                              │                                               │
│                      ┌───────┴───────┐                                       │
│                      │  API Gateway  │                                       │
│                      └───────┬───────┘                                       │
└──────────────────────────────┼──────────────────────────────────────────────┘
                               │
        ┌──────────────────────┼──────────────────────┐
        ▼                      ▼                      ▼
┌───────────────┐      ┌───────────────┐      ┌───────────────┐
│   Customer    │      │    RegimA     │      │   Business    │
│    Portal     │◄────►│  Training LMS │      │   Directory   │
└───────┬───────┘      └───────┬───────┘      └───────────────┘
        │                      │
        └──────────┬───────────┘
                   ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│                         COGNITIVE LAYER                                      │
│  ┌─────────────────────────────────────────────────────────────────────┐    │
│  │                    skintwin (Alchemist Engine)                       │    │
│  │  ┌─────────────┐  ┌─────────────┐  ┌─────────────┐                  │    │
│  │  │   Elixirs   │  │   Tensors   │  │   Vessels   │                  │    │
│  │  └─────────────┘  └─────────────┘  └─────────────┘                  │    │
│  └─────────────────────────────────────────────────────────────────────┘    │
│                                                                              │
│  ┌────────────────────────┐        ┌────────────────────────┐               │
│  │     skintwin-asi       │        │       multiskin        │               │
│  │  ┌──────────────────┐  │        │  ┌──────────────────┐  │               │
│  │  │ Deep Tree Echo   │  │◄──────►│  │ Deep Tree Echo   │  │               │
│  │  │ (Right Hemisphere)│  │        │  │ (Novelty Agent)  │  │               │
│  │  └──────────────────┘  │        │  └──────────────────┘  │               │
│  │  ┌──────────────────┐  │        │  ┌──────────────────┐  │               │
│  │  │     Marduk       │  │◄──────►│  │     Marduk       │  │               │
│  │  │ (Left Hemisphere)│  │        │  │ (Metric Agent)   │  │               │
│  │  └──────────────────┘  │        │  └──────────────────┘  │               │
│  │  ┌──────────────────┐  │        │  ┌──────────────────┐  │               │
│  │  │    JAX CEO       │  │◄──────►│  │    JAX CEO       │  │               │
│  │  │ (Orchestration)  │  │        │  │ (Neural Compute) │  │               │
│  │  └──────────────────┘  │        │  └──────────────────┘  │               │
│  └────────────────────────┘        └────────────────────────┘               │
└─────────────────────────────────────────────────────────────────────────────┘
```

## Shared Service Opportunities

### Authentication Service
All applications currently implement their own authentication. A unified authentication service using WorkOS SSO can provide single sign-on across the customer portal, training LMS, and business directory.

### Event Bus
An event-driven architecture using a message broker (Redis Streams, RabbitMQ, or Kafka) can enable real-time synchronization between applications without tight coupling.

### Shared Database Layer
Common entities (customers, products, organizations) can be stored in a shared database with application-specific views and access controls.

### AI Service Gateway
A dedicated microservice can expose the cognitive layer capabilities (skin analysis, recommendations, personalization) as a REST/GraphQL API for all applications to consume.
