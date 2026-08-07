import type { ProjectStatus } from '@prisma/client';
import { conflict } from '../../lib/errors.js';

/**
 * The project state machine (DATA_MODEL.md §2.3).
 *
 *   pending → generating → completed | failed
 *   failed  → pending                          (retry, FR-2.11)
 *
 * This is the only definition of what is legal. Everything that writes
 * `status` goes through assertTransition, so an illegal move is impossible to
 * express rather than merely discouraged.
 */
const ALLOWED: Record<ProjectStatus, ProjectStatus[]> = {
  pending: ['generating', 'failed'],
  generating: ['completed', 'failed'],
  completed: [],
  failed: ['pending'],
};

export function canTransition(from: ProjectStatus, to: ProjectStatus): boolean {
  return ALLOWED[from].includes(to);
}

export function assertTransition(from: ProjectStatus, to: ProjectStatus): void {
  if (!canTransition(from, to)) {
    throw conflict(`A ${from} project cannot become ${to}.`);
  }
}

export const TERMINAL: ProjectStatus[] = ['completed', 'failed'];
export const IN_FLIGHT: ProjectStatus[] = ['pending', 'generating'];
