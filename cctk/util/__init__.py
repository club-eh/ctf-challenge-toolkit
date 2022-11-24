"""Utility functions."""

import functools


def _fnv_1a_64(text: bytes) -> int:
	"""Computes the 64-bit FNV-1a hash of an input string.
	
	See http://www.isthe.com/chongo/tech/comp/fnv/#FNV-1a
	"""

	h = 14695981039346656037

	for byte in text:
		h ^= byte
		h *= 1099511628211

	return h

@functools.lru_cache(128)
def challenge_id_hash(challenge_id: str) -> int:
	"""Implements a variation of FNV-1a to derive a 28-bit integer hash from a string ID.
	
	Hash values will be positive integers in the range `[2^28, 2*2^28)`

	28-bits was chosen to easily fit within the unsigned portion of a signed 32-bit integer,
	without sacrificing collision probability. Given 500 challenges, the chance of a collision is below 1/2000.
	"""

	# calculate 64-bit FNV-1a hash
	fnv64hash = _fnv_1a_64(challenge_id.encode())

	# fold into 28-bit hash (http://www.isthe.com/chongo/tech/comp/fnv/#xor-fold)
	hash28 = ((fnv64hash >> 28) ^ fnv64hash) & (2**28 - 1)

	# add 2^28 for a uniform base-10 length
	return hash28 + 2**28
