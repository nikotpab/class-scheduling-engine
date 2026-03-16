# Class Scheduling Engine

This repository contains the algorithmic core and methodological foundation of a web information system designed for the **automatic generation of academic schedules**.
The project addresses the complex **Timetable Problem**, classifying it as an **Ill-Structured Problem (ISP)** that can be solved by decomposing it into **Well-Structured Problems (WSP)**.

---

# Context and Background

The development is framed within the **Proyecto Núcleo II** at **Universidad El Bosque**.
Its objective is to mitigate the risks associated with manual schedule management, such as:

* Lack of analytical visibility
* Incomplete formalization of constraints
* High probability of conflicts between teachers, classrooms, and courses

---

## Main Academic Reference

The optimization engine is based on the master's thesis:

> **Esquivel Tovar, L. L. (2014).**
> *Mathematical model for scheduling a school timetable with multi-location teachers.*
> Universidad del Valle, Cali, Colombia.

This work introduces the concept of **multi-location scheduling**, allowing the system to manage teachers who teach classes in different physical campuses while ensuring travel times and institutional consistency.

---

# Minimum Viable Product (MVP)

The **Minimum Viable Product (MVP)** focuses on delivering technical value through the following components:

## Algorithmic Assignment Engine

A Python adaptation of the mathematical optimization model.

## Drag-and-Drop Web Interface

Manual schedule management supported by **real-time conflict validation**.

## Constraint Validation

A rule-based engine that guarantees the **operability of the generated schedule**.

---

# Mathematical Model and Constraints

The system implements a **hierarchy of constraints** to guarantee valid and optimized solutions.

---

## Hard Constraints (Non-negotiable)

1. **Teacher conflict prevention**
   A teacher cannot be assigned to two places at the same time.

2. **Classroom capacity**
   Assignments must respect the physical capacity defined by the Physical Spaces Unit (UEF).

3. **Operational time window**

   * Monday to Friday: **07:00 AM – 10:00 PM**
   * Saturday: **07:00 AM – 01:00 PM**

4. **Lunch break restriction**
   Mandatory block between **12:00 PM and 01:00 PM**.

5. **Teacher availability**
   Strict compliance with each teacher’s specific availability schedule.

---

## Soft Constraints (Optimization Criteria)

* **Gap minimization**
  Maximize the efficiency of teacher time spent at the institution.

* **Consecutive day avoidance**
  Prevent sessions of the same course from occurring on consecutive days to improve the learning process.

* **Balanced weekly distribution**
  Balance the academic workload throughout the week.

---

# Technology Stack

* **Modeling Language:** LINGO 14.0 for initial mathematical formulation and instance validation.
* **Python Engine:** Implementation using the **PuLP** library for solving integer linear programming models.
* **Search Algorithms:** References to techniques such as:

  * Tabu Search
  * Simulated Annealing
  * Evolutionary Algorithms
    to address **NP-Complete complexity**.

---

# Stakeholders

The system interacts with a complex organizational environment under the **BPSC approach**.

## Program Directors

Define academic planning parameters and scheduling criteria.

## Physical Spaces Unit (UEF)

Provide the inventory of classrooms and physical resources.

## Human Talent Management (GTH)

Supply teacher employment information and availability data.

## Students and Teachers

Final users of the published academic schedules.

---

# Academic Project

Developed as part of the **Engineering Workshop: Structuring and Baseline Definition**.
