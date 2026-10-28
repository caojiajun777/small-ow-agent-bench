def prefix_sums(nums, start=0):
    out = []
    total = start
    for value in nums:
        total += value
        out.append(total)
    return out

