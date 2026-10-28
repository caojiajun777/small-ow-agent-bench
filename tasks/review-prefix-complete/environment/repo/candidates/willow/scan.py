from itertools import accumulate

def prefix_sums(nums, start=0):
    return list(accumulate(nums, initial=start))[1:]

