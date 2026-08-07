import { Prisma } from '@prisma/client';
import { conflict, notFound } from '../lib/errors.js';
import { prisma } from '../lib/prisma.js';
import { getQuota, type Quota } from './quota.service.js';

export interface MeDto {
  id: string;
  email: string;
  username: string | null;
  role: string;
  isDisabled: boolean;
  createdAt: string;
  quota: Quota;
}

const selection = {
  id: true,
  email: true,
  username: true,
  isDisabled: true,
  createdAt: true,
  role: { select: { name: true } },
} satisfies Prisma.UserSelect;

type UserRow = Prisma.UserGetPayload<{ select: typeof selection }>;

function toDto(row: UserRow, quota: Quota): MeDto {
  return {
    id: row.id,
    email: row.email,
    username: row.username,
    role: row.role.name,
    isDisabled: row.isDisabled,
    createdAt: row.createdAt.toISOString(),
    quota,
  };
}

export async function getMe(userId: string): Promise<MeDto> {
  const [row, quota] = await Promise.all([
    prisma.user.findUnique({ where: { id: userId }, select: selection }),
    getQuota(userId),
  ]);

  if (!row) throw notFound('User');

  return toDto(row, quota);
}

export async function updateMe(userId: string, data: { username?: string }): Promise<MeDto> {
  try {
    const row = await prisma.user.update({
      where: { id: userId },
      data,
      select: selection,
    });

    return toDto(row, await getQuota(userId));
  } catch (error) {
    // Checking uniqueness before writing would still race; letting the unique
    // index decide and translating the violation is the only correct version.
    if (
      error instanceof Prisma.PrismaClientKnownRequestError &&
      error.code === 'P2002'
    ) {
      throw conflict('That username is already taken.');
    }
    throw error;
  }
}
