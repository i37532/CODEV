function [u_k, nu_k_plus_1, sqrt_tilde_x_k_plus_1] = ISTA(x_k, nu_k, lambda_1, lambda_2, h)
    % Parameter definitions
    b_k = -x_k - h * nu_k;   % Corresponds to b_k in the paper
    a = h * lambda_1;         % Corresponds to hλ₁

    if b_k < -h^2 * lambda_2      % === Case 1: ξ_k = +1 ===
        %% xi_k = 1
        disc = a^2 - 4 * (b_k + lambda_2 * h^2);
        sqrt_tilde_x_k_plus_1 = (-a + sqrt(disc)) / 2;
        nu_k_plus_1 = nu_k - h * lambda_2;
        u_k = -lambda_1 * sqrt_tilde_x_k_plus_1 + nu_k_plus_1;

    elseif abs(b_k) <= h^2 * lambda_2   % === Case 2: Transition zone ===
        % xi_k = b_k / (-h^2 * lambda_2);
        sqrt_tilde_x_k_plus_1 = 0;
        nu_k_plus_1 = -x_k / h;
        u_k = nu_k_plus_1;

    else                             % === Case 3: ξ_k = −1 ===
        % xi_k = -1;
        disc = a^2 + 4 * (b_k - lambda_2 * h^2);
        sqrt_tilde_x_k_plus_1 = (-a + sqrt(disc)) / 2;
        nu_k_plus_1 = nu_k + h * lambda_2;
        u_k = lambda_1 * sqrt_tilde_x_k_plus_1 + nu_k_plus_1;
    end
end
