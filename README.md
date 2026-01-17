# SkinTwin-AI Ecosystem Design

This repository contains the comprehensive ecosystem design for the **skintwin-ai** organization. It provides a high-level overview of the integrated architecture, including the backend, frontend, and network layers that connect all repositories into a cohesive and scalable platform.

## 1. Introduction

The SkinTwin-AI ecosystem is a collection of repositories that together form a revolutionary, AI-driven beauty-tech platform. This document outlines the architecture that integrates these components, enabling seamless data flow, shared services, and a unified user experience.

## 2. Repository Ecosystem

The ecosystem is composed of several repositories, each with a specific role. The following diagram illustrates the relationships and dependencies between them:

![Repository Mapping](./diagrams/repository_mapping.png)

## 3. High-Level Architecture

The platform is designed around a microservices architecture, with a clear separation between the frontend, backend, and AI/cognitive layers. The following diagram provides a high-level overview of the entire ecosystem:

![Ecosystem Architecture](./diagrams/ecosystem_architecture.png)

### 3.1. Frontend Architecture

The frontend layer is built as a monorepo containing three primary applications: the Customer Portal, the Training LMS, and the Business Directory. These applications share a common UI library and design system to ensure a consistent user experience.

[**Read more about the Frontend Architecture](./design/frontend_architecture.md)**

### 3.2. Backend Architecture

The backend is composed of several microservices, each responsible for a specific business domain. These services are designed to be independently scalable and deployable.

[**Read more about the Backend Architecture](./design/backend_architecture.md)**

### 3.3. Network & API Gateway Architecture

A secure and scalable network layer connects all the components of the ecosystem. An API Gateway serves as the single entry point for all frontend applications, providing routing, authentication, and rate limiting.

[**Read more about the Network & API Gateway Architecture](./design/network_architecture.md)**

## 4. Data Flow

The following diagram illustrates the flow of data between the various components of the ecosystem, from user interaction to backend processing and external integrations:

![Data Flow Diagram](./diagrams/data_flow.png)

## 5. Design Documents

This repository contains detailed design documents for each architectural layer:

- [**Repository Analysis**](./analysis/repository_analysis.md)
- [**Integration Mapping**](./analysis/integration_mapping.md)
- [**Backend Architecture**](./design/backend_architecture.md)
- [**Frontend Architecture**](./design/frontend_architecture.md)
- [**Network & API Gateway Architecture**](./design/network_architecture.md)

## 6. Diagrams

All architectural diagrams are available in the `/diagrams` directory:

- [Ecosystem Architecture Diagram](./diagrams/ecosystem_architecture.png)
- [Data Flow Diagram](./diagrams/data_flow.png)
- [Repository Mapping Diagram](./diagrams/repository_mapping.png)
