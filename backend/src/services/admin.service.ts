import { Prisma } from '@prisma/client';
import { forbidden, notFound } from '../lib/errors.js';
import { prisma } from '../lib/prisma.js';
import { buildPage, cursorFilter, decodeCursor, type Page } from '../lib/pagination.js';
import type { RoleName } from '../middleware/authorize.js';

export interface AdminUserDto {
  id: string;
  email: string;
  username: string | null;
  role: string;
  isDisabled: boolean;
  projectCount: number;
  createdAt: string;
}

interface ListParams {
  limit: number;
  cursor?: string;
  q?: string;
  role?: RoleName;
  isDisabled?: boolean;
}

const selection = {
  id: true,
  email: true,
  username: true,
  isDisabled: true,
  createdAt: true,
  role: { select: { name: true } },
  _count: { select: { projects: true } },
} satisfies Prisma.UserSelect;

function toDto(row: Prisma.UserGetPayload<{ select: typeof selection }>): AdminUserDto {
  return {
    id: row.id,
    email: row.email,
    username: row.username,
    role: row.role.name,
    isDisabled: row.isDisabled,
    projectCount: row._count.projects,
    createdAt: row.createdAt.toISOString(),
  };
}

export async function listUsers(params: ListParams): Promise<Page<AdminUserDto>> {
  const cursor = decodeCursor(params.cursor);

  const where: Prisma.UserWhereInput = {
    ...cursorFilter(cursor),
    ...(params.q
      ? {
          OR: [
            { email: { contains: params.q, mode: 'insensitive' } },
            { username: { contains: params.q, mode: 'insensitive' } },
          ],
        }
      : {}),
    ...(params.role ? { role: { name: params.role } } : {}),
    ...(params.isDisabled === undefined ? {} : { isDisabled: params.isDisabled }),
  };

  const rows = await prisma.user.findMany({
    where,
    select: selection,
    orderBy: [{ createdAt: 'desc' }, { id: 'desc' }],
    take: params.limit + 1, // the extra row is how hasMore is determined
  });

  const page = buildPage(
    rows.map((r) => ({ ...r, createdAt: r.createdAt })),
    params.limit,
  );

  return { items: page.items.map(toDto), page: page.page };
}

export async function updateUser(
  actingAdminId: string,
  targetId: string,
  data: { isDisabled?: boolean; role?: RoleName },
): Promise<AdminUserDto> {
  // FR-4.6. Without this an admin can lock themselves out, or demote the last
  // admin and leave the project with no way back in.
  if (actingAdminId === targetId) {
    throw forbidden('You cannot change your own role or disable your own account.');
  }

  const roleRow = data.role
    ? await prisma.role.findUnique({ where: { name: data.role } })
    : null;

  if (data.role && !roleRow) throw notFound('Role');

  try {
    const row = await prisma.user.update({
      where: { id: targetId },
      data: {
        ...(data.isDisabled === undefined ? {} : { isDisabled: data.isDisabled }),
        ...(roleRow ? { roleId: roleRow.id } : {}),
      },
      select: selection,
    });

    return toDto(row);
  } catch (error) {
    if (error instanceof Prisma.PrismaClientKnownRequestError && error.code === 'P2025') {
      throw notFound('User');
    }
    throw error;
  }
}

export interface StatsDto {
  totals: { users: number; activeUsers: number; projects: number };
  projectsByStatus: Record<string, number>;
  projectsByProvider: Record<string, number>;
  failureRate: number;
  daily: { date: string; created: number; completed: number; failed: number }[];
}

export async function getStats(days: number): Promise<StatsDto> {
  const since = new Date(Date.now() - days * 86_400_000);

  const [users, activeUsers, projects, byStatus, byProvider, daily] = await Promise.all([
    prisma.user.count(),
    prisma.user.count({ where: { isDisabled: false } }),
    prisma.videoProject.count({ where: { deletedAt: null } }),
    prisma.videoProject.groupBy({
      by: ['status'],
      where: { deletedAt: null },
      _count: { _all: true },
    }),
    prisma.videoProject.groupBy({
      by: ['provider'],
      where: { deletedAt: null },
      _count: { _all: true },
    }),
    // Date bucketing has no Prisma equivalent, so this one is raw. Parameterised,
    // never interpolated.
    prisma.$queryRaw<{ date: Date; created: bigint; completed: bigint; failed: bigint }[]>`
      select
        date_trunc('day', created_at)::date                       as date,
        count(*)                                                  as created,
        count(*) filter (where status = 'completed')              as completed,
        count(*) filter (where status = 'failed')                 as failed
      from public.video_projects
      where created_at >= ${since} and deleted_at is null
      group by 1
      order by 1 desc
    `,
  ]);

  const statusCounts = Object.fromEntries(byStatus.map((r) => [r.status, r._count._all]));
  const completed = statusCounts['completed'] ?? 0;
  const failed = statusCounts['failed'] ?? 0;
  const finished = completed + failed;

  return {
    totals: { users, activeUsers, projects },
    projectsByStatus: {
      pending: statusCounts['pending'] ?? 0,
      generating: statusCounts['generating'] ?? 0,
      completed,
      failed,
    },
    projectsByProvider: Object.fromEntries(byProvider.map((r) => [r.provider, r._count._all])),
    // Denominator is finished generations, not all of them — counting in-flight
    // work as a success would make the rate drift with load.
    failureRate: finished === 0 ? 0 : Number((failed / finished).toFixed(4)),
    daily: daily.map((row) => ({
      date: row.date.toISOString().slice(0, 10),
      created: Number(row.created),
      completed: Number(row.completed),
      failed: Number(row.failed),
    })),
  };
}
