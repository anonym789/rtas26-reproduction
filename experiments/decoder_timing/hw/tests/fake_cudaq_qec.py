"""Stand-in for CUDA-Q QEC in tests: a decoder whose answers depend only on the syndrome."""


class _Result:
    def __init__(self, s, n):
        k = int(sum(s))
        self.opt_results = {"num_iter": k % 7 + 1}
        self.converged = k % 3 != 0
        self.result = [(k + j) % 2 if j < 5 else 0 for j in range(n)]


class _Batch:
    def __init__(self, S):
        self.converged = [sum(s) % 3 != 0 for s in S]


class _Decoder:
    def __init__(self, H):
        self.n = H.shape[1]

    def decode(self, s):
        return _Result(s, self.n)

    def decode_batch(self, S):
        return _Batch(S)

    def get_version(self):
        return "fake 1.0"


def get_decoder(name, H, **kwargs):
    return _Decoder(H)
