function [u_k, nu_k_plus_1] = ESTA(x_k, nu_k, lambda_1, lambda_2, h)
% Explicit Euler discretization of Super-Twisting Algorithm controller
% x_k: Current state x(k)
% nu_k: Current internal variable ν(k)
% lambda_1, lambda_2: Control parameters λ₁, λ₂
% h: Sampling time (step size)

% Calculate control input u(k)
u_k = -lambda_1 * sqrt(abs(x_k)) * sign(x_k) + nu_k;

% Update internal variable ν(k+1)
nu_k_plus_1 = nu_k - h * lambda_2 * sign(x_k);
end
