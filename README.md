# AyuSetu AI

> AI-powered multimodal patient case-taking system for the AyuSetu platform.

## Overview

AyuSetu AI is an AI-driven patient case-taking system designed to simplify and structure the clinical history-taking process.

The system combines conversational AI, speech recognition, document intelligence, patient memory, clinical information extraction, red-flag detection, and structured clinical summarization.

The objective is to enable a voice-first and patient-friendly case-taking experience while keeping clinical control with a defined clinical ontology, rules, and physician verification.

---

## Core Principle

> **Ontology owns the interview; the model owns only the wording.**

The AI does not freely decide what clinical information to collect.

A controlled clinical ontology and interview planner determine the required information, while the conversational model generates natural-language questions.

---

## System Architecture

```text
                    AYUSETU AI
                        |
          +-------------+-------------+
          |                           |
     VOICE PIPELINE              CLINICAL AI
          |                           |
     +----+----+                +-----+------+
     |         |                |            |
    ASR      TTS           Extraction    Document AI
     |         |                |            |
     +----+----+                +-----+------+
          |                           |
          |                     Patient Memory
          |                           |
          +-------------+-------------+
                        |
                Clinical Ontology
                        |
                 Question Planner
                        |
                Conversational AI
                        |
             +----------+----------+
             |                     |
        Red-Flag Engine      Clinical Summary
             |                     |
             +----------+----------+
                        |
                Physician Review
